"""Puanlama modu aday seçimi (OnboardingPicker): ısınma, keşif, netleştirme."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import duckdb
import numpy as np

from app.api.schemas import (
    OnboardingBatch,
    OnboardingCard,
    OnboardingProgress,
    OnboardingStage,
    TasteGroupChoice,
    TasteInsights,
    TastePreferences,
)
from app.config import RecommenderSettings
from app.db import Database
from app.services.taste_groups import GROUPS_BY_ID, TASTE_GROUPS, TasteGroup

TURKISH = "tr"
LANGUAGE_NAMES = {
    "ja": "Japonca",
    "ko": "Korece",
    "fr": "Fransızca",
    "es": "İspanyolca",
    "it": "İtalyanca",
    "de": "Almanca",
    "hi": "Hintçe",
    "zh": "Çince",
    "cn": "Çince",
    "ru": "Rusça",
    "pt": "Portekizce",
}
DECADE_YEARS = 10
NEUTRAL_PROPENSITY = 0.5  # Hakkında henüz cevap olmayan tür veya dönem


@dataclass(frozen=True)
class Candidate:
    tmdb_id: int
    title_tr: str
    title_original: str
    year: int | None
    poster_path: str | None
    genres: tuple[str, ...]
    directors: tuple[str, ...]
    language: str | None = None


def stage_for(rated: int, rec: RecommenderSettings) -> OnboardingStage:
    """Aşama verilen puan sayısına bağlıdır: "izlemedim" denen kart bilgi getirmez."""
    if rated < rec.onboarding_warmup_ratings:
        return "warmup"
    if rated < rec.onboarding_explore_ratings:
        return "explore"
    return "refine"


def _decade(year: int | None) -> int | None:
    return None if year is None else year - year % DECADE_YEARS


def _decay(rated: int, rec: RecommenderSettings, hit_rate: float) -> float:
    """0-1 ilerleme. İzleme oranı düşükse yavaşlar: kullanıcı tanınmış filmlerde kalır."""
    progress = min(rated / rec.onboarding_explore_ratings, 1.0)
    return progress * min(hit_rate / rec.onboarding_hit_target, 1.0)


def pool_size(rated: int, rec: RecommenderSettings, hit_rate: float = NEUTRAL_PROPENSITY) -> int:
    """Puan arttıkça havuz büyür: en tanınmış filmlerden daha az bilinenlere iner."""
    span = rec.onboarding_pool_end - rec.onboarding_pool_start
    return round(rec.onboarding_pool_start + span * _decay(rated, rec, hit_rate))


def popularity_weight(
    rated: int, rec: RecommenderSettings, hit_rate: float = NEUTRAL_PROPENSITY
) -> float:
    """Puan arttıkça popülerliğin skordaki payı azalır."""
    span = rec.onboarding_pop_weight_end - rec.onboarding_pop_weight_start
    return rec.onboarding_pop_weight_start + span * _decay(rated, rec, hit_rate)


def watch_propensity[K](
    seen: Counter[K],
    unseen: Counter[K],
    strength: float,
    overall: float,
    priors: Mapping[K, float] | None = None,
) -> dict[K, float]:
    """Başlangıç eğilimine çekilmiş oran: (izlenen + s·öncül) / (gösterilen + s)."""
    start = priors or {}
    return {
        key: (seen[key] + strength * start.get(key, overall)) / (seen[key] + unseen[key] + strength)
        for key in seen.keys() | unseen.keys()
    }


def preference_priors(
    all_genres: Iterable[str],
    preferred: set[str],
    overall: float,
    rated: int,
    rec: RecommenderSettings,
) -> dict[str, float]:
    """Seçilen kategorilerin başlangıç eğilimi; puan arttıkça genel orana doğru esner."""
    if not preferred:
        return {}
    influence = max(
        rec.onboarding_pref_influence_end, 1.0 - rated / rec.onboarding_pref_relax_ratings
    )
    return {
        genre: overall
        + influence
        * (
            (rec.onboarding_pref_selected if genre in preferred else rec.onboarding_pref_other)
            - overall
        )
        for genre in all_genres
    }


@dataclass(frozen=True)
class Affinity:
    genres: dict[str, float]
    decades: dict[int | None, float]
    # Hiç sınanmamış tür/dönem/dil kullanıcının genel oranıyla başlar; böylece geride kalmaz.
    default: float = NEUTRAL_PROPENSITY
    # Kullanıcının seçtiği kategorilerden gelen, henüz cevaplanmamış tür başlangıçları.
    genre_defaults: dict[str, float] = field(default_factory=dict)
    languages: dict[str | None, float] = field(default_factory=dict)


def _lift(propensity: float, overall: float) -> float:
    """Eğilimi genel izleme oranına göre 0-1'e taşır (genel oranda 0,5)."""
    total = propensity + overall
    return propensity / total if total > 0 else NEUTRAL_PROPENSITY


def candidate_fit(c: Candidate, affinity: Affinity, rec: RecommenderSettings) -> float:
    """Filmin türü, dönemi ve dili kullanıcının izleme alışkanlığına ne kadar uyuyor (0-1)."""
    overall = affinity.default
    genres = [affinity.genres.get(g, affinity.genre_defaults.get(g, overall)) for g in c.genres]
    genre = sum(genres) / len(genres) if genres else overall
    decade = affinity.decades.get(_decade(c.year), overall)
    language = affinity.languages.get(c.language, overall)
    return (
        rec.onboarding_fit_genre_share * _lift(genre, overall)
        + rec.onboarding_fit_decade_share * _lift(decade, overall)
        + rec.onboarding_fit_language_share * _lift(language, overall)
    )


def turkish_interval(affinity: Affinity, rec: RecommenderSettings) -> int:
    """Kaç kartta bir Türk filmi: izleyende sıklaşır, izlemeyende seyrekleşir."""
    propensity = affinity.languages.get(TURKISH, affinity.default)
    span = rec.onboarding_tr_every_max - rec.onboarding_tr_every_min
    return round(rec.onboarding_tr_every_max - span * propensity)


def apply_turkish_quota(
    picks: list[Candidate],
    tr_pool: list[Candidate],
    position: int,
    every: int,
    previous_directors: tuple[str, ...] = (),
) -> list[Candidate]:
    """Keşif ve netleştirme kartlarında sırası gelen kartı Türk filmiyle değiştirir."""
    used = {c.tmdb_id for c in picks}
    available = [c for c in tr_pool if c.tmdb_id not in used]
    out: list[Candidate] = []
    last = previous_directors
    for slot, card in enumerate(picks):
        chosen = card
        if (position + slot + 1) % every == 0:
            replacement = next((c for c in available if _allowed(c, set(), last)), None)
            if replacement is not None:
                available.remove(replacement)
                chosen = replacement
        out.append(chosen)
        last = chosen.directors
    return out


def rank_by_relevance(
    pool: list[Candidate], rated: int, rec: RecommenderSettings, affinity: Affinity
) -> list[Candidate]:
    """Popülerlik sırasını önceki cevaplara uygunlukla birleştirip yeniden sıralar."""
    n = len(pool)
    if n < 2:
        return pool
    weight = popularity_weight(rated, rec, affinity.default)

    def score(item: tuple[int, Candidate]) -> float:
        index, candidate = item
        popularity = 1.0 - index / (n - 1)
        fit = candidate_fit(candidate, affinity, rec)
        return weight * popularity + rec.onboarding_fit_weight * fit

    return [c for _, c in sorted(enumerate(pool), key=score, reverse=True)]


def _allowed(c: Candidate, used: set[int], last_directors: tuple[str, ...]) -> bool:
    return c.tmdb_id not in used and not set(c.directors) & set(last_directors)


def _best_balanced(
    pool: list[Candidate],
    used: set[int],
    last_directors: tuple[str, ...],
    genre_seen: Counter[str],
    decade_seen: Counter[int | None],
    window: int,
) -> Candidate | None:
    """En popüler `window` aday içinden tür ve on yılı en az görülmüş olanı seçer."""

    def imbalance(c: Candidate) -> float:
        genre = sum(genre_seen[g] for g in c.genres) / max(len(c.genres), 1)
        return genre + decade_seen[_decade(c.year)]

    allowed = [c for c in pool if _allowed(c, used, last_directors)][:window]
    return min(allowed, key=imbalance) if allowed else None


def pick_warmup(
    pool: list[Candidate],
    tr_pool: list[Candidate],
    count: int,
    position: int,
    tr_every: int,
    genre_seen: Counter[str],
    decade_seen: Counter[int | None],
    window: int,
    previous_directors: tuple[str, ...] = (),
) -> list[Candidate]:
    """Popüler filmleri dengeli dağıtır; her `tr_every`. kart Türk filmidir (varsa)."""
    genres = Counter(genre_seen)
    decades = Counter(decade_seen)
    picks: list[Candidate] = []
    used: set[int] = set()
    last = previous_directors
    for slot in range(count):
        wants_turkish = (position + slot + 1) % tr_every == 0
        card = None
        if wants_turkish:
            card = _best_balanced(tr_pool, used, last, genres, decades, window)
        if card is None:
            card = _best_balanced(pool, used, last, genres, decades, window)
        if card is None:
            break
        picks.append(card)
        used.add(card.tmdb_id)
        genres.update(card.genres)
        decades[_decade(card.year)] += 1
        last = card.directors
    return picks


def pick_farthest(
    pool: list[Candidate],
    vectors: np.ndarray,
    anchors: np.ndarray,
    count: int,
    previous_directors: tuple[str, ...] = (),
) -> list[Candidate]:
    """Farthest-point sampling: bilinen filmlere en az benzeyen adayları sırayla seçer."""
    if not pool:
        return []
    nearest = (vectors @ anchors.T).max(axis=1) if anchors.shape[0] else np.full(len(pool), -1.0)
    picks: list[Candidate] = []
    used: set[int] = set()
    last = previous_directors
    for _ in range(count):
        best = -1
        for i in np.argsort(nearest, kind="stable"):
            if _allowed(pool[int(i)], used, last):
                best = int(i)
                break
        if best < 0:
            break
        card = pool[best]
        picks.append(card)
        used.add(card.tmdb_id)
        last = card.directors
        nearest = np.maximum(nearest, vectors @ vectors[best])
    return picks


def boundary_scores(
    vectors: np.ndarray, centroids: np.ndarray, mid_similarity: float
) -> np.ndarray:
    """Küçük skor daha bilgilendirici: iki kümenin sınırı veya tek merkeze orta mesafe."""
    sims = vectors @ centroids.T
    if centroids.shape[0] >= 2:
        top_two = np.sort(sims, axis=1)[:, -2:]
        return top_two[:, 1] - top_two[:, 0]
    return np.abs(sims[:, 0] - mid_similarity)


def pick_lowest(
    pool: list[Candidate],
    scores: np.ndarray,
    count: int,
    previous_directors: tuple[str, ...] = (),
) -> list[Candidate]:
    picks: list[Candidate] = []
    used: set[int] = set()
    last = previous_directors
    for i in np.argsort(scores, kind="stable"):
        if len(picks) == count:
            break
        card = pool[int(i)]
        if _allowed(card, used, last):
            picks.append(card)
            used.add(card.tmdb_id)
            last = card.directors
    return picks


def _load_pool(
    cur: duckdb.DuckDBPyConnection,
    exclude: list[int],
    limit: int,
    language: str | None = None,
    needs_embedding: bool = False,
) -> list[Candidate]:
    rows = cur.execute(
        "SELECT m.tmdb_id, m.title_tr, m.title_original, year(m.release_date), m.poster_path,"
        " m.original_language,"
        " (SELECT list(g.name_tr ORDER BY g.id) FROM movie_genre mg"
        "   JOIN genres g ON g.id = mg.genre_id WHERE mg.movie_id = m.tmdb_id),"
        " (SELECT list(p.name ORDER BY p.name) FROM movie_person mp"
        "   JOIN people p ON p.id = mp.person_id"
        "   WHERE mp.movie_id = m.tmdb_id AND mp.role = 'director')"
        " FROM movies m"
        " WHERE m.poster_path IS NOT NULL"
        " AND m.tmdb_id NOT IN (SELECT movie_id FROM ratings)"
        " AND m.tmdb_id NOT IN (SELECT movie_id FROM onboarding_skips)"
        " AND m.tmdb_id NOT IN (SELECT unnest(?::BIGINT[]))"
        " AND (?::VARCHAR IS NULL OR m.original_language = ?)"
        " AND (NOT ?::BOOLEAN OR m.embedding IS NOT NULL)"
        " ORDER BY m.vote_count DESC NULLS LAST, m.tmdb_id LIMIT ?",
        [exclude, language, language, needs_embedding, limit],
    ).fetchall()
    return [
        Candidate(r[0], r[1], r[2], r[3], r[4], tuple(r[6] or ()), tuple(r[7] or ()), r[5])
        for r in rows
    ]


def _stack(column: np.ndarray) -> np.ndarray:
    return np.stack(list(column)).astype(np.float32) if len(column) else np.empty((0, 0))


def _vectors(cur: duckdb.DuckDBPyConnection, ids: list[int]) -> np.ndarray:
    """Verilen ID'lerin embedding'lerini aynı sırayla döndürür (embedding'i olanlar)."""
    data = cur.execute(
        "SELECT v.id, m.embedding FROM (SELECT unnest(?::BIGINT[]) AS id,"
        " generate_subscripts(?::BIGINT[], 1) AS pos) v"
        " JOIN movies m ON m.tmdb_id = v.id WHERE m.embedding IS NOT NULL ORDER BY v.pos",
        [ids, ids],
    ).fetchnumpy()
    return _stack(data["embedding"])


def _answered_ids(cur: duckdb.DuckDBPyConnection) -> set[int]:
    rows = cur.execute("SELECT movie_id FROM ratings UNION SELECT movie_id FROM onboarding_skips")
    return {int(r[0]) for r in rows.fetchall()}


def _rated_ids(cur: duckdb.DuckDBPyConnection) -> list[int]:
    return [int(r[0]) for r in cur.execute("SELECT movie_id FROM ratings").fetchall()]


def _seen_balance(
    cur: duckdb.DuckDBPyConnection, ids: list[int]
) -> tuple[Counter[str], Counter[int | None]]:
    genres = cur.execute(
        "SELECT g.name_tr, count(*) FROM movie_genre mg JOIN genres g ON g.id = mg.genre_id"
        " WHERE mg.movie_id IN (SELECT unnest(?::BIGINT[])) GROUP BY 1",
        [ids],
    ).fetchall()
    decades = cur.execute(
        "SELECT year(release_date), count(*) FROM movies"
        " WHERE tmdb_id IN (SELECT unnest(?::BIGINT[])) GROUP BY 1",
        [ids],
    ).fetchall()
    decade_seen: Counter[int | None] = Counter()
    for year, n in decades:
        decade_seen[_decade(year)] += n
    return Counter({g: n for g, n in genres}), decade_seen


def _directors_of(cur: duckdb.DuckDBPyConnection, tmdb_id: int | None) -> tuple[str, ...]:
    if tmdb_id is None:
        return ()
    rows = cur.execute(
        "SELECT p.name FROM movie_person mp JOIN people p ON p.id = mp.person_id"
        " WHERE mp.movie_id = ? AND mp.role = 'director'",
        [tmdb_id],
    ).fetchall()
    return tuple(r[0] for r in rows)


def _load_affinity(
    cur: duckdb.DuckDBPyConnection, rec: RecommenderSettings, rated: int
) -> Affinity:
    """Puanlanan film izlenmiş, "izlemedim" denen film izlenmemiş sayılır."""
    strength = rec.onboarding_fit_strength
    answers = (
        "(SELECT movie_id, TRUE AS seen FROM ratings"
        " UNION ALL SELECT movie_id, FALSE AS seen FROM onboarding_skips) a"
    )
    genre_rows = cur.execute(
        "SELECT g.name_tr, count(*) FILTER (WHERE a.seen), count(*) FILTER (WHERE NOT a.seen)"
        " FROM " + answers + " JOIN movie_genre mg ON mg.movie_id = a.movie_id"
        " JOIN genres g ON g.id = mg.genre_id GROUP BY 1"
    ).fetchall()
    year_rows = cur.execute(
        "SELECT year(m.release_date), count(*) FILTER (WHERE a.seen),"
        " count(*) FILTER (WHERE NOT a.seen)"
        " FROM " + answers + " JOIN movies m ON m.tmdb_id = a.movie_id GROUP BY 1"
    ).fetchall()
    language_rows = cur.execute(
        "SELECT m.original_language, count(*) FILTER (WHERE a.seen),"
        " count(*) FILTER (WHERE NOT a.seen)"
        " FROM " + answers + " JOIN movies m ON m.tmdb_id = a.movie_id GROUP BY 1"
    ).fetchall()
    language_seen: Counter[str | None] = Counter({r[0]: r[1] for r in language_rows})
    language_unseen: Counter[str | None] = Counter({r[0]: r[2] for r in language_rows})
    genre_seen: Counter[str] = Counter({r[0]: r[1] for r in genre_rows})
    genre_unseen: Counter[str] = Counter({r[0]: r[2] for r in genre_rows})
    decade_seen: Counter[int | None] = Counter()
    decade_unseen: Counter[int | None] = Counter()
    for year, seen, unseen in year_rows:
        decade_seen[_decade(year)] += seen
        decade_unseen[_decade(year)] += unseen
    total_seen = sum(decade_seen.values())
    total = total_seen + sum(decade_unseen.values())
    overall = (total_seen + strength * NEUTRAL_PROPENSITY) / (total + strength)
    groups = _selected_groups(cur)
    catalog = [r[0] for r in cur.execute("SELECT name_tr FROM genres").fetchall()]
    preferred = {genre for group in groups for genre in group.genres}
    priors = preference_priors(catalog, preferred, overall, rated, rec)
    domestic = any(group.language == TURKISH for group in groups)
    language_priors = (
        preference_priors([TURKISH], {TURKISH}, overall, rated, rec) if domestic else {}
    )
    languages = watch_propensity(language_seen, language_unseen, strength, overall, language_priors)
    for language, prior in language_priors.items():
        languages.setdefault(language, prior)
    return Affinity(
        genres=watch_propensity(genre_seen, genre_unseen, strength, overall, priors),
        decades=watch_propensity(decade_seen, decade_unseen, strength, overall),
        default=overall,
        genre_defaults=priors,
        languages=languages,
    )


def _ranked_pool(
    cur: duckdb.DuckDBPyConnection,
    rec: RecommenderSettings,
    exclude: list[int],
    rated: int,
    affinity: Affinity,
) -> list[Candidate]:
    limit = pool_size(rated, rec, affinity.default)
    pool = _load_pool(cur, exclude, limit, needs_embedding=True)
    return rank_by_relevance(pool, rated, rec, affinity)


def _warmup(
    cur: duckdb.DuckDBPyConnection,
    rec: RecommenderSettings,
    exclude: list[int],
    answered: set[int],
    position: int,
    rated: int,
    count: int,
    last: tuple[str, ...],
    affinity: Affinity,
) -> list[Candidate]:
    limit = pool_size(rated, rec, affinity.default)
    pool = rank_by_relevance(_load_pool(cur, exclude, limit), rated, rec, affinity)
    tr_pool = rank_by_relevance(
        _load_pool(cur, exclude, rec.onboarding_tr_pool, language=TURKISH), rated, rec, affinity
    )
    genre_seen, decade_seen = _seen_balance(cur, sorted(answered | set(exclude)))
    return pick_warmup(
        pool,
        tr_pool,
        count,
        position,
        turkish_interval(affinity, rec),
        genre_seen,
        decade_seen,
        rec.onboarding_warmup_window,
        last,
    )


def _explore(
    cur: duckdb.DuckDBPyConnection,
    rec: RecommenderSettings,
    exclude: list[int],
    rated: int,
    count: int,
    last: tuple[str, ...],
    affinity: Affinity,
) -> list[Candidate]:
    pool = _ranked_pool(cur, rec, exclude, rated, affinity)[: rec.onboarding_shortlist]
    if not pool:
        return []
    vectors = _vectors(cur, [c.tmdb_id for c in pool])
    anchors = _vectors(cur, _rated_ids(cur) + exclude)
    return pick_farthest(pool, vectors, anchors, count, last)


def _refine(
    cur: duckdb.DuckDBPyConnection,
    rec: RecommenderSettings,
    exclude: list[int],
    rated: int,
    count: int,
    last: tuple[str, ...],
    affinity: Affinity,
) -> list[Candidate]:
    data = cur.execute(
        "SELECT centroid FROM taste_clusters WHERE NOT is_negative AND centroid IS NOT NULL"
    ).fetchnumpy()
    centroids = _stack(data["centroid"])
    if centroids.shape[0] == 0:  # Küme yoksa keşfe devam edilir.
        return _explore(cur, rec, exclude, rated, count, last, affinity)
    pool = _ranked_pool(cur, rec, exclude, rated, affinity)[: rec.onboarding_shortlist]
    if not pool:
        return []
    vectors = _vectors(cur, [c.tmdb_id for c in pool])
    scores = boundary_scores(vectors, centroids, rec.onboarding_refine_mid_similarity)
    return pick_lowest(pool, scores, count, last)


def next_cards(
    db: Database,
    rec: RecommenderSettings,
    exclude: list[int],
    previous: int | None,
    count: int | None,
) -> OnboardingBatch:
    """Sıradaki kartları seçer. `exclude`: istemcinin kuyruğundaki veya yolda olan filmler."""
    cur = db.cursor()
    answered = _answered_ids(cur)
    position = len(answered | set(exclude))
    wanted = min(count or rec.onboarding_batch, rec.onboarding_max_batch)
    rated = len(_rated_ids(cur))
    stage = stage_for(rated, rec)
    last = _directors_of(cur, previous)

    affinity = _load_affinity(cur, rec, rated)
    picks: list[Candidate] = []
    if stage == "explore":
        picks = _explore(cur, rec, exclude, rated, wanted, last, affinity)
    elif stage == "refine":
        picks = _refine(cur, rec, exclude, rated, wanted, last, affinity)
    if picks:
        tr_pool = rank_by_relevance(
            _load_pool(cur, exclude, rec.onboarding_tr_pool, language=TURKISH), rated, rec, affinity
        )
        picks = apply_turkish_quota(picks, tr_pool, position, turkish_interval(affinity, rec), last)
    else:  # Isınma aşaması veya embedding henüz yoksa popüler havuz kullanılır.
        picks = _warmup(cur, rec, exclude, answered, position, rated, wanted, last, affinity)

    return OnboardingBatch(
        stage=stage,
        cards=[
            OnboardingCard(
                tmdb_id=c.tmdb_id,
                title_tr=c.title_tr,
                title_original=c.title_original,
                year=c.year,
                poster_path=c.poster_path,
                directors=list(c.directors),
            )
            for c in picks
        ],
    )


def _selected_groups(cur: duckdb.DuckDBPyConnection) -> list[TasteGroup]:
    rows = cur.execute("SELECT group_id FROM preferred_groups").fetchall()
    return [GROUPS_BY_ID[r[0]] for r in rows if r[0] in GROUPS_BY_ID]


def taste_preferences(db: Database) -> TastePreferences:
    selected = {group.id for group in _selected_groups(db.cursor())}
    return TastePreferences(
        groups=[
            TasteGroupChoice(
                id=g.id, name=g.name, films=g.films, tags=g.tags, selected=g.id in selected
            )
            for g in TASTE_GROUPS
        ],
        completed=bool(selected),
    )


def set_taste_preferences(db: Database, group_ids: list[str]) -> TastePreferences:
    """Seçimi tümüyle değiştirir; bilinmeyen grup kimlikleri yok sayılır."""
    valid = list(dict.fromkeys(i for i in group_ids if i in GROUPS_BY_ID))
    if not valid:
        raise ValueError("Geçerli grup yok")
    cur = db.cursor()
    cur.execute("BEGIN TRANSACTION")
    try:
        cur.execute("DELETE FROM preferred_groups")
        cur.execute("INSERT INTO preferred_groups (group_id) SELECT unnest(?::VARCHAR[])", [valid])
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    return taste_preferences(db)


def taste_insights(cur: duckdb.DuckDBPyConnection, rec: RecommenderSettings) -> TasteInsights:
    """Kullanıcının izleme alışkanlıklarının okunabilir özeti."""
    row = cur.execute(
        "SELECT (SELECT count(*) FROM ratings), (SELECT count(*) FROM onboarding_skips)"
    ).fetchone()
    assert row is not None
    rated, skipped = int(row[0]), int(row[1])
    affinity = _load_affinity(cur, rec, rated)
    every = turkish_interval(affinity, rec)
    if rated + skipped < rec.insight_min_answers:
        return TasteInsights(
            rated=rated, skipped=skipped, favorites=[], avoid=[], turkish_every=every
        )
    overall = affinity.default
    high = overall * rec.insight_high
    low = overall * rec.insight_low
    favorites = [g for g, p in sorted(affinity.genres.items(), key=lambda x: -x[1]) if p >= high]
    candidates = [(p, g) for g, p in affinity.genres.items() if p <= low]
    candidates += [
        (p, LANGUAGE_NAMES[k])
        for k, p in affinity.languages.items()
        if p <= low and k in LANGUAGE_NAMES
    ]
    candidates += [(p, f"{k}'ler") for k, p in affinity.decades.items() if p <= low and k]
    return TasteInsights(
        rated=rated,
        skipped=skipped,
        favorites=favorites[: rec.insight_favorite_count],
        avoid=[name for _, name in sorted(candidates)[: rec.insight_avoid_count]],
        turkish_every=every,
    )


def progress(db: Database, rec: RecommenderSettings) -> OnboardingProgress:
    cur = db.cursor()
    row = cur.execute(
        "SELECT (SELECT count(*) FROM ratings), (SELECT count(*) FROM onboarding_skips)"
    ).fetchone()
    assert row is not None
    rated, skipped = int(row[0]), int(row[1])
    return OnboardingProgress(
        rated=rated,
        skipped=skipped,
        target=rec.onboarding_target_ratings,
        stage=stage_for(rated, rec),
    )
