"""Film araması: başlık eşleşmesi, BM25 (fts) ve yazım hatası toleransı."""

import unicodedata

from app.api.schemas import SearchResult
from app.config import RecommenderSettings
from app.db import Database

_FTS_SCHEMA = "fts_main_movies"


def fold_text(text: str) -> str:
    """Küçük harf, Türkçe ı/İ ve aksan katlama: 'Kış' -> 'kis'. SQL tarafıyla aynı kuralı izler."""
    lowered = text.replace("İ", "i").lower().replace("ı", "i")
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", lowered) if unicodedata.category(c) != "Mn"
    )
    return " ".join(stripped.split())


def search_movies(
    db: Database, query: str, limit: int | None, rec: RecommenderSettings
) -> list[SearchResult]:
    folded = fold_text(query)
    if not folded:
        return []
    cur = db.cursor()
    has_index = cur.execute(
        "SELECT 1 FROM duckdb_schemas() WHERE schema_name = ?", [_FTS_SCHEMA]
    ).fetchone()
    if has_index is None:  # Henüz katalog import edilmemiş.
        return []
    capped = min(limit or rec.search_default_limit, rec.search_max_limit)
    cur.execute(
        """
        WITH s AS (
            SELECT m.tmdb_id, m.title_tr, m.title_original, year(m.release_date) AS year,
                   m.poster_path, m.vote_average, m.vote_count,
                   fts_main_movies.match_bm25(m.tmdb_id, $raw) AS bm25,
                   strip_accents(replace(lower(m.title_tr), 'ı', 'i')) AS a,
                   strip_accents(replace(lower(m.title_original), 'ı', 'i')) AS b
            FROM movies m
        ), t AS (
            SELECT *,
                   greatest(jaro_winkler_similarity(a, $q), jaro_winkler_similarity(b, $q)) AS jw,
                   CASE WHEN a = $q OR b = $q THEN 0
                        WHEN starts_with(a, $q) OR starts_with(b, $q) THEN 1
                        WHEN contains(a, $q) OR contains(b, $q) THEN 2
                        WHEN bm25 IS NOT NULL THEN 3
                        ELSE 4 END AS tier
            FROM s
        )
        SELECT t.tmdb_id, t.title_tr, t.title_original, t.year, t.poster_path, t.vote_average,
               r.score AS my_rating, w.movie_id IS NOT NULL AS in_watchlist
        FROM t
        LEFT JOIN ratings r ON r.movie_id = t.tmdb_id
        LEFT JOIN watchlist w ON w.movie_id = t.tmdb_id
        WHERE t.tier < 4 OR t.jw >= $threshold
        ORDER BY t.tier,
                 CASE WHEN t.tier <= 2 THEN t.vote_count::DOUBLE ELSE t.jw END DESC,
                 t.vote_count DESC NULLS LAST
        LIMIT $limit
        """,
        {
            "raw": query.strip(),
            "q": folded,
            "threshold": rec.search_fuzzy_threshold,
            "limit": capped,
        },
    )
    names = [d[0] for d in cur.description]
    return [SearchResult(**dict(zip(names, r, strict=True))) for r in cur.fetchall()]
