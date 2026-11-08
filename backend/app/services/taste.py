"""Zevk modeli: puanlardan zevk kümeleri ve itme profili çıkarır."""

from dataclasses import dataclass

import duckdb
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from app.api.schemas import TasteCluster, TasteMovie, TasteResponse
from app.config import RecommenderSettings
from app.db import Database
from app.services.embedding import l2_normalize
from app.services.onboarding import taste_insights

POSITIVE_SCORES = (4, 5)
NEGATIVE_SCORES = (1, 2)


@dataclass(frozen=True)
class ClusterStats:
    members: np.ndarray  # girdi satır indeksleri
    centroid: np.ndarray
    weight: float
    memberships: np.ndarray  # üyelerin merkeze kosinüs benzerliği


def weighted_centroid(vectors: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Ağırlıklı ortalama, birim uzunluğa getirilmiş."""
    mean = np.average(vectors, axis=0, weights=weights)
    return l2_normalize(mean[np.newaxis, :])[0]


def _fit(vectors: np.ndarray, weights: np.ndarray, k: int, rec: RecommenderSettings) -> np.ndarray:
    model = KMeans(n_clusters=k, n_init=rec.cluster_n_init, random_state=rec.cluster_random_state)
    return model.fit_predict(vectors, sample_weight=weights)


def choose_k(
    vectors: np.ndarray,
    weights: np.ndarray,
    k_min: int,
    k_max: int,
    rec: RecommenderSettings,
) -> np.ndarray | None:
    """Silhouette skoru (cosine) en yüksek k'nın etiketlerini döndürür; geçerli k yoksa None."""
    best: np.ndarray | None = None
    best_score = -np.inf
    for k in range(k_min, min(k_max, len(vectors) - 1) + 1):
        labels = _fit(vectors, weights, k, rec)
        if len(np.unique(labels)) < 2:  # Tüm noktalar aynıysa ayrım yapılamaz.
            continue
        score = silhouette_score(vectors, labels, metric="cosine")
        if score > best_score:
            best, best_score = labels, score
    return best


def merge_small_clusters(
    vectors: np.ndarray, weights: np.ndarray, labels: np.ndarray, min_size: int
) -> np.ndarray:
    """`min_size`'tan küçük kümeleri, en küçüğünden başlayarak en yakın kümeye eritir."""
    labels = labels.copy()
    while True:
        ids, sizes = np.unique(labels, return_counts=True)
        if len(ids) < 2 or sizes.min() >= min_size:
            return labels
        smallest = ids[np.argmin(sizes)]
        centroids = {i: weighted_centroid(vectors[labels == i], weights[labels == i]) for i in ids}
        others = [i for i in ids if i != smallest]
        target = max(others, key=lambda i: float(centroids[smallest] @ centroids[i]))
        labels[labels == smallest] = target


def cluster_positive(
    vectors: np.ndarray, weights: np.ndarray, rec: RecommenderSettings
) -> np.ndarray:
    """Her satırın küme etiketini döndürür. Veri azsa hepsi tek "genel zevk" kümesindedir."""
    single = np.zeros(len(vectors), dtype=int)
    if len(vectors) < rec.cluster_min_positive:
        return single
    k_max = min(rec.cluster_k_max, len(vectors) // rec.cluster_k_per_n)
    if k_max < rec.cluster_k_min:
        return single
    labels = choose_k(vectors, weights, rec.cluster_k_min, k_max, rec)
    if labels is None:
        return single
    return merge_small_clusters(vectors, weights, labels, rec.cluster_min_size)


def cluster_negative(
    vectors: np.ndarray, weights: np.ndarray, rec: RecommenderSettings
) -> np.ndarray:
    single = np.zeros(len(vectors), dtype=int)
    if len(vectors) <= rec.negative_split_threshold:
        return single
    labels = choose_k(vectors, weights, rec.cluster_k_min, rec.negative_max_clusters, rec)
    return single if labels is None else labels


def summarize(vectors: np.ndarray, weights: np.ndarray, labels: np.ndarray) -> list[ClusterStats]:
    """Kümeleri ağırlığa göre sıralı özetler; eşitlikte en küçük satır indeksi önce gelir."""
    out: list[ClusterStats] = []
    for label in np.unique(labels):
        members = np.flatnonzero(labels == label)
        centroid = weighted_centroid(vectors[members], weights[members])
        out.append(
            ClusterStats(
                members=members,
                centroid=centroid,
                weight=float(weights[members].sum()),
                memberships=vectors[members] @ centroid,
            )
        )
    out.sort(key=lambda c: (-c.weight, int(c.members[0])))
    return out


def _load(cur: duckdb.DuckDBPyConnection, sql: str, params: list) -> tuple[list[int], np.ndarray]:
    data = cur.execute(sql, params).fetchnumpy()
    ids = [int(i) for i in data["movie_id"]]
    if not ids:
        return [], np.empty((0, 0), dtype=np.float32)
    return ids, l2_normalize(np.stack(list(data["embedding"])).astype(np.float32))


def _load_positive(
    cur: duckdb.DuckDBPyConnection, rec: RecommenderSettings
) -> tuple[list[int], np.ndarray, np.ndarray]:
    cur.execute(
        "SELECT r.movie_id, r.score FROM ratings r JOIN movies m ON m.tmdb_id = r.movie_id"
        " WHERE r.score IN (SELECT unnest(?::INTEGER[])) AND m.embedding IS NOT NULL"
        " ORDER BY r.movie_id",
        [list(POSITIVE_SCORES)],
    )
    scores = [int(r[1]) for r in cur.fetchall()]
    ids, vectors = _load(
        cur,
        "SELECT r.movie_id, m.embedding FROM ratings r JOIN movies m ON m.tmdb_id = r.movie_id"
        " WHERE r.score IN (SELECT unnest(?::INTEGER[])) AND m.embedding IS NOT NULL"
        " ORDER BY r.movie_id",
        [list(POSITIVE_SCORES)],
    )
    weights = np.array([rec.rating_weights[s] for s in scores], dtype=np.float32)
    return ids, vectors, weights


def _load_negative(
    cur: duckdb.DuckDBPyConnection, rec: RecommenderSettings
) -> tuple[list[int], np.ndarray, np.ndarray]:
    """Puanı 1-2 olanlar ve "ilgimi çekmedi" denenler. Film puanlıysa puanı geçerlidir."""
    source = (
        " FROM ("
        "  SELECT movie_id, score FROM ratings WHERE score IN (SELECT unnest(?::INTEGER[]))"
        "  UNION ALL"
        "  SELECT DISTINCT movie_id, NULL FROM recommendation_feedback"
        "  WHERE action = 'dismissed' AND movie_id NOT IN (SELECT movie_id FROM ratings)"
        " ) n JOIN movies m ON m.tmdb_id = n.movie_id"
        " WHERE m.embedding IS NOT NULL ORDER BY n.movie_id"
    )
    negative = list(NEGATIVE_SCORES)
    rows = cur.execute("SELECT n.score" + source, [negative]).fetchall()
    ids, vectors = _load(cur, "SELECT n.movie_id, m.embedding" + source, [negative])
    # KMeans negatif ağırlık kabul etmez; itme gücü mutlak değerle taşınır.
    weights = np.array(
        [abs(rec.dismissed_weight if r[0] is None else rec.rating_weights[r[0]]) for r in rows],
        dtype=np.float32,
    )
    return ids, vectors, weights


def _top_keywords(cur: duckdb.DuckDBPyConnection, movie_ids: list[int], limit: int) -> list[str]:
    rows = cur.execute(
        "SELECT k.name FROM movie_keyword mk JOIN keywords k ON k.id = mk.keyword_id"
        " WHERE mk.movie_id IN (SELECT unnest(?::BIGINT[]))"
        " GROUP BY k.id, k.name, k.df ORDER BY count(*) DESC, k.df, k.name LIMIT ?",
        [movie_ids, limit],
    ).fetchall()
    return [r[0] for r in rows]


def _insert_clusters(
    cur: duckdb.DuckDBPyConnection,
    ids: list[int],
    stats: list[ClusterStats],
    is_negative: bool,
    rec: RecommenderSettings,
) -> None:
    for cluster in stats:
        member_ids = [ids[int(i)] for i in cluster.members]
        row = cur.execute(
            "INSERT INTO taste_clusters (centroid, weight, size, top_keywords, is_negative,"
            " computed_at) VALUES (?::FLOAT[1024], ?, ?, ?, ?, current_timestamp::TIMESTAMP)"
            " RETURNING id",
            [
                cluster.centroid.tolist(),
                cluster.weight,
                len(member_ids),
                _top_keywords(cur, member_ids, rec.cluster_top_keywords),
                is_negative,
            ],
        ).fetchone()
        assert row is not None
        cur.execute(
            "INSERT INTO taste_cluster_movie (cluster_id, movie_id, membership)"
            " SELECT ?, unnest(?::BIGINT[]), unnest(?::DOUBLE[])",
            [int(row[0]), member_ids, cluster.memberships.tolist()],
        )


def recompute_taste(db: Database, rec: RecommenderSettings) -> int:
    """Kümeleri baştan hesaplar, tek transaction'da değiştirir; küme sayısını döndürür."""
    cur = db.cursor()
    pos_ids, pos_vectors, pos_weights = _load_positive(cur, rec)
    neg_ids, neg_vectors, neg_weights = _load_negative(cur, rec)
    pos_stats = (
        summarize(pos_vectors, pos_weights, cluster_positive(pos_vectors, pos_weights, rec))
        if pos_ids
        else []
    )
    neg_stats = (
        summarize(neg_vectors, neg_weights, cluster_negative(neg_vectors, neg_weights, rec))
        if neg_ids
        else []
    )

    cur.execute("BEGIN TRANSACTION")
    try:
        cur.execute("DELETE FROM taste_cluster_movie")
        cur.execute("DELETE FROM taste_clusters")
        _insert_clusters(cur, pos_ids, pos_stats, False, rec)
        _insert_clusters(cur, neg_ids, neg_stats, True, rec)
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    return len(pos_stats) + len(neg_stats)


def ratings_since_last_recompute(cur: duckdb.DuckDBPyConnection) -> int:
    row = cur.execute(
        "SELECT count(*) FROM ratings WHERE rated_at > coalesce("
        " (SELECT max(created_at) FROM jobs WHERE type = 'recompute_taste'),"
        " TIMESTAMP '1970-01-01')"
    ).fetchone()
    assert row is not None
    return int(row[0])


def _auto_title(cur: duckdb.DuckDBPyConnection, cluster_id: int, rec: RecommenderSettings) -> str:
    """Faz 6'daki LLM isimlerine kadar kümenin baskın türlerinden Türkçe başlık."""
    genres = cur.execute(
        "SELECT g.name_tr FROM taste_cluster_movie tcm"
        " JOIN movie_genre mg ON mg.movie_id = tcm.movie_id"
        " JOIN genres g ON g.id = mg.genre_id WHERE tcm.cluster_id = ?"
        " GROUP BY g.name_tr ORDER BY count(*) DESC, g.name_tr LIMIT ?",
        [cluster_id, rec.cluster_title_genres],
    ).fetchall()
    share = cur.execute(
        "SELECT avg(CASE WHEN m.original_language = 'tr' THEN 1.0 ELSE 0.0 END)"
        " FROM taste_cluster_movie tcm JOIN movies m ON m.tmdb_id = tcm.movie_id"
        " WHERE tcm.cluster_id = ?",
        [cluster_id],
    ).fetchone()
    names = [r[0] for r in genres]
    if share and share[0] is not None and share[0] >= rec.cluster_domestic_share:
        names.insert(0, "Yerli")
    return " · ".join(names) if names else "Genel zevk"


def get_taste(db: Database, rec: RecommenderSettings) -> TasteResponse:
    cur = db.cursor()
    clusters = cur.execute(
        "SELECT id, label, description, weight, size, top_keywords, is_negative, computed_at"
        " FROM taste_clusters ORDER BY is_negative, weight DESC, id"
    ).fetchall()
    positive = cur.execute(
        "SELECT count(*) FROM ratings WHERE score IN (SELECT unnest(?::INTEGER[]))",
        [list(POSITIVE_SCORES)],
    ).fetchone()
    assert positive is not None

    out: list[TasteCluster] = []
    for c in clusters:
        typical = cur.execute(
            "SELECT m.tmdb_id, m.title_tr, m.poster_path, tcm.membership"
            " FROM taste_cluster_movie tcm JOIN movies m ON m.tmdb_id = tcm.movie_id"
            " WHERE tcm.cluster_id = ? ORDER BY tcm.membership DESC, m.tmdb_id LIMIT ?",
            [c[0], rec.cluster_typical_display],
        ).fetchall()
        out.append(
            TasteCluster(
                id=c[0],
                label=c[1],
                auto_title=_auto_title(cur, c[0], rec),
                description=c[2],
                weight=c[3],
                size=c[4],
                top_keywords=c[5] or [],
                is_negative=c[6],
                typical=[
                    TasteMovie(tmdb_id=t[0], title_tr=t[1], poster_path=t[2], membership=t[3])
                    for t in typical
                ],
            )
        )
    return TasteResponse(
        clusters=[c for c in out if not c.is_negative],
        negatives=[c for c in out if c.is_negative],
        computed_at=clusters[0][7] if clusters else None,
        positive_count=int(positive[0]),
        min_positive=rec.cluster_min_positive,
        insights=taste_insights(cur, rec),
    )
