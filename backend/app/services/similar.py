"""Buna benzer filmler: embedding uzayında kaba kuvvet komşu araması."""

from app.api.schemas import SimilarMovie
from app.db import Database


class MovieNotFoundError(LookupError):
    pass


class EmbeddingMissingError(LookupError):
    pass


def similar_movies(db: Database, tmdb_id: int, limit: int) -> list[SimilarMovie]:
    cur = db.cursor()
    row = cur.execute(
        "SELECT embedding IS NOT NULL FROM movies WHERE tmdb_id = ?", [tmdb_id]
    ).fetchone()
    if row is None:
        raise MovieNotFoundError(tmdb_id)
    if not row[0]:
        raise EmbeddingMissingError(tmdb_id)
    cur.execute(
        "SELECT m.tmdb_id, m.title_tr, m.title_original, m.release_date, m.poster_path,"
        " m.vote_average, 1 - array_cosine_distance(m.embedding, q.e) AS similarity"
        " FROM movies m, (SELECT embedding AS e FROM movies WHERE tmdb_id = ?) q"
        " WHERE m.embedding IS NOT NULL AND m.tmdb_id <> ?"
        " ORDER BY array_cosine_distance(m.embedding, q.e) LIMIT ?",
        [tmdb_id, tmdb_id, limit],
    )
    names = [d[0] for d in cur.description]
    return [SimilarMovie(**dict(zip(names, r, strict=True))) for r in cur.fetchall()]
