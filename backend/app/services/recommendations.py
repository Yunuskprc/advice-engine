"""Öneri motoru: aday topla, filtrele, skorla, çeşitlendir, açıkla."""

from dataclasses import dataclass

import duckdb
import numpy as np
import scipy.sparse as sp

from app.api.schemas import (
    FilterOption,
    ProviderOut,
    RecommendationOptions,
    RecommendationRequest,
    RecommendationResponse,
    RecommendedMovie,
)
from app.config import RecommenderSettings
from app.db import Database
from app.services.features import FeatureSet, load_features
from app.services.scoring import (
    RecommendationScorer,
    ScoreInputs,
    bayesian_quality,
    hybrid_similarity,
    mmr_select,
    popularity_percentile,
    weighted_jaccard,
)
from app.services.taste import POSITIVE_SCORES
from app.services.vector_index import VectorIndex

FAVORITE_SCORE = 5


class ClusterNotFoundError(LookupError):
    pass


# Sabit SQL parçası: tüm kullanıcı değerleri parametredir.
_FILTERS = """
    m.embedding IS NOT NULL
    AND m.vote_count >= $min_votes
    AND m.tmdb_id NOT IN (SELECT movie_id FROM ratings)
    AND m.tmdb_id NOT IN (SELECT movie_id FROM watchlist)
    AND m.tmdb_id NOT IN (SELECT movie_id FROM recommendation_feedback WHERE action = 'dismissed')
    AND m.tmdb_id NOT IN (SELECT unnest($exclude::BIGINT[]))
    AND ($year_min::INTEGER IS NULL OR year(m.release_date) >= $year_min)
    AND ($year_max::INTEGER IS NULL OR year(m.release_date) <= $year_max)
    AND ($runtime_min::INTEGER IS NULL OR m.runtime >= $runtime_min)
    AND ($runtime_max::INTEGER IS NULL OR m.runtime <= $runtime_max)
    AND (NOT $domestic OR m.original_language = 'tr')
    AND (NOT $foreign OR m.original_language IS DISTINCT FROM 'tr')
    AND (len($genres_in::BIGINT[]) = 0 OR m.tmdb_id IN (
        SELECT movie_id FROM movie_genre WHERE genre_id IN (SELECT unnest($genres_in::BIGINT[]))))
    AND m.tmdb_id NOT IN (
        SELECT movie_id FROM movie_genre WHERE genre_id IN (SELECT unnest($genres_out::BIGINT[])))
    AND (len($providers::BIGINT[]) = 0 OR m.tmdb_id IN (
        SELECT movie_id FROM movie_providers
        WHERE provider_id IN (SELECT unnest($providers::BIGINT[]))))
"""

_ALLOWED_SQL = "SELECT m.tmdb_id FROM movies m WHERE " + _FILTERS


@dataclass(frozen=True)
class Cluster:
    id: int
    centroid: np.ndarray
    weight: float


def _vectors(cur: duckdb.DuckDBPyConnection, ids: list[int]) -> np.ndarray:
    data = cur.execute(
        "SELECT m.embedding FROM (SELECT unnest($ids::BIGINT[]) AS id,"
        " generate_subscripts($ids::BIGINT[], 1) AS pos) v"
        " JOIN movies m ON m.tmdb_id = v.id ORDER BY v.pos",
        {"ids": ids},
    ).fetchnumpy()
    return np.stack(list(data["embedding"])).astype(np.float32)


def _clusters(cur: duckdb.DuckDBPyConnection) -> list[Cluster]:
    rows = cur.execute(
        "SELECT id, weight FROM taste_clusters WHERE NOT is_negative ORDER BY weight DESC, id"
    ).fetchall()
    data = cur.execute(
        "SELECT centroid FROM taste_clusters WHERE NOT is_negative ORDER BY weight DESC, id"
    ).fetchnumpy()
    return [
        Cluster(int(r[0]), np.asarray(c, dtype=np.float32), float(r[1]))
        for r, c in zip(rows, data["centroid"], strict=True)
    ]


def pick_surprise_cluster(
    clusters: list[Cluster], exponent: float, rng: np.random.Generator
) -> Cluster:
    """p ∝ ağırlık^üs: küçük kümeler de şans bulur."""
    weights = np.array([c.weight for c in clusters], dtype=np.float64) ** exponent
    return clusters[int(rng.choice(len(clusters), p=weights / weights.sum()))]


class CandidateGenerator:
    def __init__(
        self, cur: duckdb.DuckDBPyConnection, rec: RecommenderSettings, index: VectorIndex
    ) -> None:
        self.cur = cur
        self.rec = rec
        self.index = index

    def generate(
        self, centroid: np.ndarray, typical: np.ndarray, request: RecommendationRequest
    ) -> list[int]:
        """Küme merkezine en yakınlar ve tipik filmlerin komşuları, tekilleştirilmiş."""
        rec, f = self.rec, request.filters
        vectors = np.vstack([centroid[np.newaxis, :], typical]) if len(typical) else centroid[None]
        allowed = self.cur.execute(
            _ALLOWED_SQL,
            {
                "min_votes": rec.candidate_min_vote_count,
                "exclude": request.exclude,
                "year_min": f.year_min,
                "year_max": f.year_max,
                "runtime_min": f.runtime_min,
                "runtime_max": f.runtime_max,
                "domestic": f.origin == "domestic",
                "foreign": f.origin == "foreign",
                "genres_in": f.genres_include,
                "genres_out": f.genres_exclude,
                "providers": f.providers,
            },
        ).fetchnumpy()["tmdb_id"]
        counts = [rec.candidate_center_top_n] + [rec.candidate_per_typical_n] * len(typical)
        seen: dict[int, None] = {}
        for ids in self.index.nearest(vectors, np.asarray(allowed, dtype=np.int64), counts):
            seen.update(dict.fromkeys(ids))
        return list(seen)


@dataclass(frozen=True)
class Refs:
    ids: list[int]
    scores: list[int]
    titles: list[str]


def _positive_refs(cur: duckdb.DuckDBPyConnection) -> Refs:
    rows = cur.execute(
        "SELECT r.movie_id, r.score, m.title_tr FROM ratings r"
        " JOIN movies m ON m.tmdb_id = r.movie_id"
        " WHERE r.score IN (SELECT unnest(?::INTEGER[])) AND m.embedding IS NOT NULL"
        " ORDER BY r.movie_id",
        [list(POSITIVE_SCORES)],
    ).fetchall()
    return Refs([int(r[0]) for r in rows], [int(r[1]) for r in rows], [r[2] for r in rows])


def _typical_ids(cur: duckdb.DuckDBPyConnection, cluster_id: int, limit: int) -> list[int]:
    rows = cur.execute(
        "SELECT tcm.movie_id FROM taste_cluster_movie tcm"
        " JOIN movies m ON m.tmdb_id = tcm.movie_id"
        " WHERE tcm.cluster_id = ? AND m.embedding IS NOT NULL"
        " ORDER BY tcm.membership DESC, tcm.movie_id LIMIT ?",
        [cluster_id, limit],
    ).fetchall()
    return [int(r[0]) for r in rows]


def _matrix_or_empty(cur: duckdb.DuckDBPyConnection, ids: list[int], dim: int) -> np.ndarray:
    return _vectors(cur, ids) if ids else np.empty((0, dim), dtype=np.float32)


def _max_or_zero(values: np.ndarray, n_rows: int) -> np.ndarray:
    return values.max(axis=1) if values.shape[1] else np.zeros(n_rows)


def _repulsion(cur: duckdb.DuckDBPyConnection, candidates: np.ndarray) -> np.ndarray:
    data = cur.execute(
        "SELECT centroid FROM taste_clusters WHERE is_negative AND centroid IS NOT NULL"
    ).fetchnumpy()
    if len(data["centroid"]) == 0:
        return np.zeros(len(candidates))
    centroids = np.stack(list(data["centroid"])).astype(np.float32)
    return (candidates @ centroids.T).max(axis=1)


def _watchlist_ids(cur: duckdb.DuckDBPyConnection) -> list[int]:
    rows = cur.execute(
        "SELECT w.movie_id FROM watchlist w JOIN movies m ON m.tmdb_id = w.movie_id"
        " WHERE m.embedding IS NOT NULL ORDER BY w.movie_id"
    ).fetchall()
    return [int(r[0]) for r in rows]


@dataclass(frozen=True)
class CandidateMeta:
    title_tr: str
    title_original: str
    year: int | None
    runtime: int | None
    poster_path: str | None
    vote_average: float | None
    vote_count: int
    popularity: float


def _meta(cur: duckdb.DuckDBPyConnection, ids: list[int]) -> list[CandidateMeta]:
    rows = cur.execute(
        "SELECT m.tmdb_id, m.title_tr, m.title_original, year(m.release_date), m.runtime,"
        " m.poster_path, m.vote_average, coalesce(m.vote_count, 0), coalesce(m.popularity, 0)"
        " FROM movies m WHERE m.tmdb_id IN (SELECT unnest(?::BIGINT[]))",
        [ids],
    ).fetchall()
    by_id = {int(r[0]): CandidateMeta(*r[1:]) for r in rows}
    return [by_id[i] for i in ids]


def _providers(cur: duckdb.DuckDBPyConnection, ids: list[int]) -> dict[int, list[ProviderOut]]:
    rows = cur.execute(
        "SELECT movie_id, provider_id, provider_name, type, logo_path FROM movie_providers"
        " WHERE movie_id IN (SELECT unnest(?::BIGINT[])) ORDER BY type, provider_name",
        [ids],
    ).fetchall()
    out: dict[int, list[ProviderOut]] = {i: [] for i in ids}
    for movie_id, pid, name, kind, logo in rows:
        out[int(movie_id)].append(ProviderOut(id=pid, name=name, type=kind, logo_path=logo))
    return out


def _names(cur: duckdb.DuckDBPyConnection, features: FeatureSet) -> dict[tuple[str, str], str]:
    """Açıklamada geçebilecek keyword ve kişi adları."""
    keyword_ids = sorted(
        {int(v) for fs in features.by_movie.values() for k, v in fs if k == "keyword"}
    )
    person_ids = sorted(
        {int(v) for fs in features.by_movie.values() for k, v in fs if k in ("director", "writer")}
    )
    names: dict[tuple[str, str], str] = {}
    for row in cur.execute(
        "SELECT id, name FROM keywords WHERE id IN (SELECT unnest(?::BIGINT[]))", [keyword_ids]
    ).fetchall():
        names[("keyword", str(row[0]))] = row[1]
    for row in cur.execute(
        "SELECT id, name FROM people WHERE id IN (SELECT unnest(?::BIGINT[]))", [person_ids]
    ).fetchall():
        names[("person", str(row[0]))] = row[1]
    return names


def explain(
    movie_id: int,
    ref_sims: np.ndarray,
    refs: Refs,
    features: FeatureSet,
    names: dict[tuple[str, str], str],
    rec: RecommenderSettings,
) -> str:
    """Deterministik açıklama: en benzer puanlı filmler, ortak etiketler, aynı yönetmen/senarist."""
    if len(refs.ids) == 0:
        return "Zevk kümenize yakın bir film."
    order = np.argsort(-ref_sims, kind="stable")[: rec.explain_ref_count]
    chosen = [int(i) for i in order]
    titles = " ve ".join(f"{refs.titles[i]} ({refs.scores[i]}★)" for i in chosen)
    own = features.by_movie[movie_id]
    shared: set[tuple[str, str]] = set()
    for i in chosen:
        shared |= own & features.by_movie[refs.ids[i]]
    keywords = sorted(
        (v for k, v in shared if k == "keyword"), key=lambda v: (features.df.get(v, 0), v)
    )
    labels = [names[("keyword", v)] for v in keywords[: rec.explain_keyword_count]]
    text = f"{titles} ile benzer"
    text += f": {', '.join(labels)}." if labels else "."

    for kind, label in (("director", "Aynı yönetmen"), ("writer", "Aynı senarist")):
        matches = sorted(
            names[("person", v)]
            for k, v in own
            if k == kind and any((k, v) in features.by_movie[r] for r in refs.ids)
        )
        if matches:
            return f"{text} {label}: {', '.join(matches)}."
    return text


def recommend(
    db: Database,
    rec: RecommenderSettings,
    request: RecommendationRequest,
    index: VectorIndex | None = None,
    rng: np.random.Generator | None = None,
) -> RecommendationResponse:
    cur = db.cursor()
    index = index if index is not None else VectorIndex()
    index.ensure_fresh(db, cur)
    clusters = _clusters(cur)
    if not clusters:
        return RecommendationResponse(cluster_id=None, items=[])
    if request.cluster_id is None:
        cluster = pick_surprise_cluster(
            clusters, rec.surprise_weight_exponent, rng or np.random.default_rng()
        )
    else:
        matches = [c for c in clusters if c.id == request.cluster_id]
        if not matches:
            raise ClusterNotFoundError(request.cluster_id)
        cluster = matches[0]

    dim = len(cluster.centroid)
    typical_ids = _typical_ids(cur, cluster.id, rec.candidate_typical_n)
    typical = _matrix_or_empty(cur, typical_ids, dim)
    ids = CandidateGenerator(cur, rec, index).generate(cluster.centroid, typical, request)
    if not ids:
        return RecommendationResponse(cluster_id=cluster.id, items=[])

    refs = _positive_refs(cur)
    five_ids = [i for i, s in zip(refs.ids, refs.scores, strict=True) if s == FAVORITE_SCORE]
    watch_ids = _watchlist_ids(cur)
    vectors = _vectors(cur, ids)
    meta = _meta(cur, ids)
    features = load_features(cur, sorted({*ids, *typical_ids, *refs.ids}), rec)
    candidate_rows = features.rows(ids)

    def hybrid_to(other_ids: list[int], other_vectors: np.ndarray) -> np.ndarray:
        structural = weighted_jaccard_rows(candidate_rows, features, other_ids)
        return hybrid_similarity(vectors @ other_vectors.T, structural, rec)

    cluster_cos = vectors @ cluster.centroid
    if typical_ids:
        cluster_structural = weighted_jaccard_rows(candidate_rows, features, typical_ids).mean(
            axis=1
        )
    else:
        cluster_structural = np.zeros(len(ids))
    five_vectors = _matrix_or_empty(cur, five_ids, dim)
    watch_vectors = _matrix_or_empty(cur, watch_ids, dim)
    mean_row = cur.execute("SELECT avg(vote_average) FROM movies").fetchone()
    catalog_mean = float(mean_row[0]) if mean_row and mean_row[0] is not None else 0.0

    inputs = ScoreInputs(
        cluster_sim=hybrid_similarity(cluster_cos, cluster_structural, rec),
        best_five_sim=_max_or_zero(hybrid_to(five_ids, five_vectors), len(ids)),
        quality=bayesian_quality(
            np.array([m.vote_average or 0.0 for m in meta]),
            np.array([m.vote_count for m in meta]),
            rec.bayes_m,
            catalog_mean,
        ),
        repulsion_cos=_repulsion(cur, vectors),
        watchlist_cos=_max_or_zero(vectors @ watch_vectors.T, len(ids)),
        popularity=popularity_percentile(np.array([m.popularity for m in meta])),
    )
    scores = RecommendationScorer(rec).score(inputs, request.exploration)

    pool = np.argsort(-scores, kind="stable")[: rec.mmr_pool_size]
    pool_ids = [ids[int(i)] for i in pool]
    pool_rows = features.rows(pool_ids)
    pool_vectors = vectors[pool]
    pool_sim = hybrid_similarity(
        pool_vectors @ pool_vectors.T,
        weighted_jaccard(pool_rows, pool_rows, features.weights),
        rec,
    )
    directors = [
        [v for k, v in features.by_movie[movie_id] if k == "director"] for movie_id in pool_ids
    ]
    picked = mmr_select(
        scores[pool], pool_sim, directors, rec.result_count, rec.mmr_lambda, rec.max_per_director
    )

    selected = [int(pool[i]) for i in picked]
    selected_ids = [ids[i] for i in selected]
    if refs.ids:
        ref_vectors = _vectors(cur, refs.ids)
        ref_sims = hybrid_similarity(
            vectors[selected] @ ref_vectors.T,
            weighted_jaccard(
                features.rows(selected_ids), features.rows(refs.ids), features.weights
            ),
            rec,
        )
    else:
        ref_sims = np.zeros((len(selected), 0))
    names = _names(cur, features)
    providers = _providers(cur, selected_ids)

    items = [
        RecommendedMovie(
            tmdb_id=ids[i],
            title_tr=meta[i].title_tr,
            title_original=meta[i].title_original,
            year=meta[i].year,
            runtime=meta[i].runtime,
            poster_path=meta[i].poster_path,
            vote_average=meta[i].vote_average,
            providers=providers[ids[i]],
            explanation=explain(ids[i], ref_sims[row], refs, features, names, rec),
            score=float(scores[i]),
        )
        for row, i in enumerate(selected)
    ]
    return RecommendationResponse(cluster_id=cluster.id, items=items)


def weighted_jaccard_rows(
    a: sp.csr_matrix, features: FeatureSet, other_ids: list[int]
) -> np.ndarray:
    if not other_ids:
        return np.zeros((a.shape[0], 0))
    return weighted_jaccard(a, features.rows(other_ids), features.weights)


def filter_options(db: Database, rec: RecommenderSettings) -> RecommendationOptions:
    cur = db.cursor()
    genres = cur.execute("SELECT id, name_tr FROM genres ORDER BY name_tr").fetchall()
    providers = cur.execute(
        "SELECT provider_id, any_value(provider_name), any_value(logo_path)"
        " FROM movie_providers WHERE type = 'flatrate'"
        " GROUP BY provider_id ORDER BY count(*) DESC, provider_id LIMIT ?",
        [rec.filter_provider_limit],
    ).fetchall()
    return RecommendationOptions(
        genres=[FilterOption(id=g[0], name=g[1]) for g in genres],
        providers=[FilterOption(id=p[0], name=p[1], logo_path=p[2]) for p in providers],
    )
