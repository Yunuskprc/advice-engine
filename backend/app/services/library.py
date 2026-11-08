"""Puanlar, "izlemedim" kayıtları ve izleme listesi."""

import duckdb

from app.api.schemas import ProviderOut, WatchlistItem
from app.db import Database
from app.services.similar import MovieNotFoundError


def _require_movie(cur: duckdb.DuckDBPyConnection, tmdb_id: int) -> None:
    if cur.execute("SELECT 1 FROM movies WHERE tmdb_id = ?", [tmdb_id]).fetchone() is None:
        raise MovieNotFoundError(tmdb_id)


def set_rating(db: Database, tmdb_id: int, score: int) -> None:
    cur = db.cursor()
    _require_movie(cur, tmdb_id)
    cur.execute(
        "INSERT INTO ratings (movie_id, score, rated_at)"
        " VALUES (?, ?, current_timestamp::TIMESTAMP)"
        " ON CONFLICT (movie_id) DO UPDATE SET score = EXCLUDED.score,"
        " rated_at = EXCLUDED.rated_at",
        [tmdb_id, score],
    )
    # Puanlanan film artık "izlemedim" sayılmaz.
    cur.execute("DELETE FROM onboarding_skips WHERE movie_id = ?", [tmdb_id])


def delete_rating(db: Database, tmdb_id: int) -> None:
    db.cursor().execute("DELETE FROM ratings WHERE movie_id = ?", [tmdb_id])


def add_skip(db: Database, tmdb_id: int) -> None:
    cur = db.cursor()
    _require_movie(cur, tmdb_id)
    cur.execute(
        "INSERT INTO onboarding_skips (movie_id) VALUES (?) ON CONFLICT DO NOTHING", [tmdb_id]
    )


def delete_skip(db: Database, tmdb_id: int) -> None:
    db.cursor().execute("DELETE FROM onboarding_skips WHERE movie_id = ?", [tmdb_id])


def add_to_watchlist(db: Database, tmdb_id: int) -> None:
    cur = db.cursor()
    _require_movie(cur, tmdb_id)
    cur.execute("INSERT INTO watchlist (movie_id) VALUES (?) ON CONFLICT DO NOTHING", [tmdb_id])


def remove_from_watchlist(db: Database, tmdb_id: int) -> None:
    db.cursor().execute("DELETE FROM watchlist WHERE movie_id = ?", [tmdb_id])


def save_answers(db: Database, ratings: list[tuple[int, int]], skips: list[int]) -> None:
    """Bir sayfanın cevaplarını tek transaction'da yazar; katalogda olmayanlar yok sayılır."""
    rated_ids = [movie_id for movie_id, _ in ratings]
    scores = [score for _, score in ratings]
    skip_ids = [movie_id for movie_id in skips if movie_id not in set(rated_ids)]
    cur = db.cursor()
    cur.execute("BEGIN TRANSACTION")
    try:
        cur.execute(
            "INSERT INTO ratings (movie_id, score, rated_at)"
            " SELECT v.id, v.score, current_timestamp::TIMESTAMP FROM"
            " (SELECT unnest(?::BIGINT[]) AS id, unnest(?::INTEGER[]) AS score) v"
            " JOIN movies m ON m.tmdb_id = v.id"
            " ON CONFLICT (movie_id) DO UPDATE SET score = EXCLUDED.score,"
            " rated_at = EXCLUDED.rated_at",
            [rated_ids, scores],
        )
        cur.execute(
            "DELETE FROM onboarding_skips WHERE movie_id IN (SELECT unnest(?::BIGINT[]))",
            [rated_ids],
        )
        cur.execute(
            "INSERT INTO onboarding_skips (movie_id)"
            " SELECT v.id FROM (SELECT unnest(?::BIGINT[]) AS id) v"
            " JOIN movies m ON m.tmdb_id = v.id ON CONFLICT DO NOTHING",
            [skip_ids],
        )
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise


def remove_answers(db: Database, movie_ids: list[int]) -> None:
    """Son sayfayı geri almak için puan ve "izlemedim" kayıtlarını siler."""
    cur = db.cursor()
    cur.execute("DELETE FROM ratings WHERE movie_id IN (SELECT unnest(?::BIGINT[]))", [movie_ids])
    cur.execute(
        "DELETE FROM onboarding_skips WHERE movie_id IN (SELECT unnest(?::BIGINT[]))", [movie_ids]
    )


def remove_feedback(db: Database, tmdb_id: int, action: str) -> None:
    """Öneri geri bildirimini geri alır; "saved" ise film listeden de çıkar."""
    db.cursor().execute(
        "DELETE FROM recommendation_feedback WHERE movie_id = ? AND action = ?", [tmdb_id, action]
    )
    if action == "saved":
        remove_from_watchlist(db, tmdb_id)


def add_feedback(db: Database, tmdb_id: int, action: str, cluster_id: int | None) -> None:
    """Öneri geri bildirimini kaydeder; "saved" filmi izleme listesine de ekler."""
    cur = db.cursor()
    _require_movie(cur, tmdb_id)
    cur.execute(
        "INSERT INTO recommendation_feedback (movie_id, action, cluster_id) VALUES (?, ?, ?)",
        [tmdb_id, action, cluster_id],
    )
    if action == "saved":
        add_to_watchlist(db, tmdb_id)


def list_watchlist(db: Database) -> list[WatchlistItem]:
    cur = db.cursor()
    rows = cur.execute(
        "SELECT m.tmdb_id, m.title_tr, m.title_original, year(m.release_date), m.runtime,"
        " m.poster_path FROM watchlist w JOIN movies m ON m.tmdb_id = w.movie_id"
        " ORDER BY w.added_at DESC, m.tmdb_id"
    ).fetchall()
    providers: dict[int, list[ProviderOut]] = {int(r[0]): [] for r in rows}
    for movie_id, pid, name, kind, logo in cur.execute(
        "SELECT movie_id, provider_id, provider_name, type, logo_path FROM movie_providers"
        " WHERE movie_id IN (SELECT unnest(?::BIGINT[])) ORDER BY type, provider_name",
        [list(providers)],
    ).fetchall():
        providers[int(movie_id)].append(ProviderOut(id=pid, name=name, type=kind, logo_path=logo))
    return [
        WatchlistItem(
            tmdb_id=r[0],
            title_tr=r[1],
            title_original=r[2],
            year=r[3],
            runtime=r[4],
            poster_path=r[5],
            providers=providers[int(r[0])],
        )
        for r in rows
    ]
