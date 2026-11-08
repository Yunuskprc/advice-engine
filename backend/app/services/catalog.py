"""TMDB katalog importu ve günlük senkron."""

import asyncio
import gzip
import json
import logging
import tempfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from app.clients.tmdb import TmdbApi, TmdbAuthError, TmdbError
from app.config import AppSettings, RecommenderSettings
from app.db import Database
from app.services.movie_parser import ParsedMovie, parse_movie, skip_reason

log = logging.getLogger(__name__)

OnTotal = Callable[[int], None]
OnProgress = Callable[[int], None]

SKIP_NOT_FOUND = "not_found"


@dataclass
class ImportStats:
    attempted: int = 0
    stored: int = 0
    skipped: int = 0
    failed: int = 0


def _noop(_: int) -> None:
    return None


def iter_export(path: Path) -> Iterator[dict[str, Any]]:
    """Gzip'li export dosyasını satır satır okur, bozuk satırları atlar."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                log.warning("Export'ta bozuk satır atlandı")


def select_candidates(
    rows: Iterable[dict[str, Any]],
    known_ids: set[int],
    min_popularity: float,
    limit: int | None = None,
) -> list[int]:
    """Ön filtre: yetişkin olmayan, eşik üstü, bilinmeyen ID'ler; popüler olan önce."""
    found = [
        (float(r.get("popularity") or 0), int(r["id"]))
        for r in rows
        if not r.get("adult")
        and float(r.get("popularity") or 0) >= min_popularity
        and int(r["id"]) not in known_ids
    ]
    found.sort(key=lambda x: (-x[0], x[1]))
    ids = [i for _, i in found]
    return ids[:limit] if limit is not None else ids


def date_windows(start: date, end: date, max_days: int) -> list[tuple[date, date]]:
    """[start, end] aralığını en fazla `max_days` günlük (uçlar dahil) parçalara böler."""
    windows: list[tuple[date, date]] = []
    current = start
    while current <= end:
        window_end = min(current + timedelta(days=max_days - 1), end)
        windows.append((current, window_end))
        current = window_end + timedelta(days=1)
    return windows


def known_ids(cur: duckdb.DuckDBPyConnection) -> set[int]:
    rows = cur.execute("SELECT tmdb_id FROM movies UNION SELECT tmdb_id FROM skipped_tmdb_ids")
    return {int(r[0]) for r in rows.fetchall()}


def _columns(rows: list[tuple[Any, ...]], width: int) -> list[list[Any]]:
    if not rows:
        return [[] for _ in range(width)]
    return [list(c) for c in zip(*rows, strict=True)]


def _stale_flags(cur: duckdb.DuckDBPyConnection, movies: list[ParsedMovie]) -> dict[int, bool]:
    """Yeni filmler ve özeti/keyword'leri değişen filmler için True."""
    existing = cur.execute(
        "SELECT m.tmdb_id, m.overview_tr, m.overview_en,"
        " coalesce(list(k.keyword_id) FILTER (WHERE k.keyword_id IS NOT NULL), [])"
        " FROM movies m LEFT JOIN movie_keyword k ON k.movie_id = m.tmdb_id"
        " WHERE m.tmdb_id IN (SELECT unnest(?::BIGINT[]))"
        " GROUP BY ALL",
        [[m.tmdb_id for m in movies]],
    ).fetchall()
    before = {int(r[0]): (r[1], r[2], {int(k) for k in r[3]}) for r in existing}
    flags: dict[int, bool] = {}
    for m in movies:
        now = (m.overview_tr, m.overview_en, {k for k, _ in m.keywords})
        flags[m.tmdb_id] = before.get(m.tmdb_id) != now
    return flags


def write_batch(cur: duckdb.DuckDBPyConnection, movies: list[ParsedMovie]) -> None:
    """Filmleri ve ilişkilerini tek transaction'da toplu yazar. Embedding'e dokunmaz."""
    if not movies:
        return
    stale = _stale_flags(cur, movies)
    ids = [m.tmdb_id for m in movies]
    movie_rows = [
        (
            m.tmdb_id,
            m.title_tr,
            m.title_original,
            m.original_language,
            m.overview_tr,
            m.overview_en,
            m.release_date,
            m.runtime,
            m.vote_average,
            m.vote_count,
            m.popularity,
            m.poster_path,
            m.backdrop_path,
            stale[m.tmdb_id],
        )
        for m in movies
    ]
    genres = {g: name for m in movies for g, name in m.genres}
    keywords = {k: name for m in movies for k, name in m.keywords}
    people = {p.id: (p.name, p.profile_path) for m in movies for p in m.people}
    movie_genre = [(m.tmdb_id, g) for m in movies for g, _ in m.genres]
    movie_keyword = [(m.tmdb_id, k) for m in movies for k, _ in m.keywords]
    movie_person = [(m.tmdb_id, p.id, p.role, p.cast_order) for m in movies for p in m.people]
    movie_providers = [
        (m.tmdb_id, p.id, p.name, p.type, p.logo_path) for m in movies for p in m.providers
    ]

    cur.execute("BEGIN TRANSACTION")
    try:
        cur.execute(
            "INSERT INTO movies (tmdb_id, title_tr, title_original, original_language,"
            " overview_tr, overview_en, release_date, runtime, vote_average, vote_count,"
            " popularity, poster_path, backdrop_path, embedding_stale, synced_at)"
            " SELECT unnest(?::BIGINT[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),"
            " unnest(?::VARCHAR[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),"
            " unnest(?::DATE[]), unnest(?::INTEGER[]), unnest(?::DOUBLE[]), unnest(?::INTEGER[]),"
            " unnest(?::DOUBLE[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[]),"
            " unnest(?::BOOLEAN[]), current_timestamp::TIMESTAMP"
            " ON CONFLICT (tmdb_id) DO UPDATE SET"
            " title_tr = EXCLUDED.title_tr, title_original = EXCLUDED.title_original,"
            " original_language = EXCLUDED.original_language,"
            " overview_tr = EXCLUDED.overview_tr, overview_en = EXCLUDED.overview_en,"
            " release_date = EXCLUDED.release_date, runtime = EXCLUDED.runtime,"
            " vote_average = EXCLUDED.vote_average, vote_count = EXCLUDED.vote_count,"
            " popularity = EXCLUDED.popularity, poster_path = EXCLUDED.poster_path,"
            " backdrop_path = EXCLUDED.backdrop_path,"
            " embedding_stale = movies.embedding_stale OR EXCLUDED.embedding_stale,"
            " synced_at = EXCLUDED.synced_at",
            _columns(movie_rows, 14),
        )
        cur.execute(
            "INSERT INTO genres (id, name_tr)"
            " SELECT unnest(?::BIGINT[]), unnest(?::VARCHAR[])"
            " ON CONFLICT (id) DO UPDATE SET name_tr = EXCLUDED.name_tr",
            [list(genres.keys()), list(genres.values())],
        )
        cur.execute(
            "INSERT INTO keywords (id, name)"
            " SELECT unnest(?::BIGINT[]), unnest(?::VARCHAR[])"
            " ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name",
            [list(keywords.keys()), list(keywords.values())],
        )
        cur.execute(
            "INSERT INTO people (id, name, profile_path)"
            " SELECT unnest(?::BIGINT[]), unnest(?::VARCHAR[]), unnest(?::VARCHAR[])"
            " ON CONFLICT (id) DO UPDATE SET"
            " name = EXCLUDED.name, profile_path = EXCLUDED.profile_path",
            [list(people.keys()), [v[0] for v in people.values()], [v[1] for v in people.values()]],
        )
        for sql in (
            "DELETE FROM movie_genre WHERE movie_id IN (SELECT unnest(?::BIGINT[]))",
            "DELETE FROM movie_keyword WHERE movie_id IN (SELECT unnest(?::BIGINT[]))",
            "DELETE FROM movie_person WHERE movie_id IN (SELECT unnest(?::BIGINT[]))",
            "DELETE FROM movie_providers WHERE movie_id IN (SELECT unnest(?::BIGINT[]))",
        ):
            cur.execute(sql, [ids])
        cur.execute(
            "INSERT INTO movie_genre (movie_id, genre_id)"
            " SELECT unnest(?::BIGINT[]), unnest(?::BIGINT[])",
            _columns(movie_genre, 2),
        )
        cur.execute(
            "INSERT INTO movie_keyword (movie_id, keyword_id)"
            " SELECT unnest(?::BIGINT[]), unnest(?::BIGINT[])",
            _columns(movie_keyword, 2),
        )
        cur.execute(
            "INSERT INTO movie_person (movie_id, person_id, role, cast_order)"
            " SELECT unnest(?::BIGINT[]), unnest(?::BIGINT[]), unnest(?::VARCHAR[]),"
            " unnest(?::INTEGER[])",
            _columns(movie_person, 4),
        )
        cur.execute(
            "INSERT INTO movie_providers (movie_id, provider_id, provider_name, type, logo_path)"
            " SELECT unnest(?::BIGINT[]), unnest(?::BIGINT[]), unnest(?::VARCHAR[]),"
            " unnest(?::VARCHAR[]), unnest(?::VARCHAR[])",
            _columns(movie_providers, 5),
        )
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise


def write_skips(cur: duckdb.DuckDBPyConnection, skips: list[tuple[int, str]]) -> None:
    if skips:
        cur.execute(
            "INSERT INTO skipped_tmdb_ids (tmdb_id, reason)"
            " SELECT unnest(?::BIGINT[]), unnest(?::VARCHAR[])"
            " ON CONFLICT (tmdb_id) DO NOTHING",
            _columns(skips, 2),
        )


def finalize_catalog(cur: duckdb.DuckDBPyConnection) -> None:
    """Keyword df değerlerini günceller, fts index'ini yeniden kurar."""
    cur.execute(
        "UPDATE keywords SET df = x.n FROM ("
        " SELECT k.id, count(mk.movie_id) AS n FROM keywords k"
        " LEFT JOIN movie_keyword mk ON mk.keyword_id = k.id GROUP BY k.id"
        ") x WHERE keywords.id = x.id"
    )
    cur.execute(
        "PRAGMA create_fts_index('movies', 'tmdb_id', 'title_tr', 'title_original',"
        " stemmer = 'none', stopwords = 'none', strip_accents = 1, lower = 1, overwrite = 1)"
    )


async def fetch_and_store(
    client: TmdbApi,
    db: Database,
    ids: list[int],
    settings: AppSettings,
    rec: RecommenderSettings,
    apply_filter: bool = True,
    on_progress: OnProgress = _noop,
) -> ImportStats:
    """ID'leri eşzamanlı çeker ve batch'lerle yazar. Kilitsizdir: tek event loop thread'i yazar."""
    stats = ImportStats(attempted=len(ids))
    cur = db.cursor()
    pending = iter(ids)
    movies: list[ParsedMovie] = []
    skips: list[tuple[int, str]] = []
    done = 0

    def flush() -> None:
        write_batch(cur, movies)
        write_skips(cur, skips)
        stats.stored += len(movies)
        stats.skipped += len(skips)
        movies.clear()
        skips.clear()

    async def worker() -> None:
        nonlocal done
        for tmdb_id in pending:
            try:
                raw = await client.get_movie(tmdb_id)
            except TmdbAuthError:
                raise
            except TmdbError as e:
                # Skip listesine yazılmaz: bir sonraki çalıştırmada yeniden denenir.
                log.warning("Film alınamadı (#%s): %s", tmdb_id, e)
                stats.failed += 1
            else:
                if raw is None:
                    if apply_filter:
                        skips.append((tmdb_id, SKIP_NOT_FOUND))
                else:
                    reason = skip_reason(raw, settings) if apply_filter else None
                    if reason:
                        skips.append((tmdb_id, reason))
                    else:
                        movies.append(parse_movie(raw, settings, rec.feat_cast_top_n))
                if len(movies) + len(skips) >= settings.tmdb_batch_size:
                    flush()
            done += 1
            on_progress(done)

    try:
        async with asyncio.TaskGroup() as tg:
            for _ in range(min(settings.tmdb_max_concurrency, max(len(ids), 1))):
                tg.create_task(worker())
    except ExceptionGroup as eg:
        raise eg.exceptions[0] from eg
    finally:
        flush()
    return stats


async def _export_candidates(
    client: TmdbApi, known: set[int], settings: AppSettings, today: date, limit: int | None
) -> list[int]:
    with tempfile.TemporaryDirectory() as tmp:
        path = await client.download_export(Path(tmp), today)
        return select_candidates(iter_export(path), known, settings.tmdb_min_popularity, limit)


async def _priority_candidates(
    client: TmdbApi, known: set[int], settings: AppSettings
) -> list[int]:
    """Popülerlik eşiğine takılan yerli filmleri dil listesinden doğrudan bulur."""
    found: dict[int, None] = {}
    for language in settings.tmdb_priority_languages:
        page = 1
        while page <= settings.tmdb_discover_max_pages:
            data = await client.discover_language(language, page)
            found.update(
                dict.fromkeys(int(r["id"]) for r in data.get("results", []) if r["id"] not in known)
            )
            if page >= int(data.get("total_pages") or 1):
                break
            page += 1
    return list(found)


async def _new_candidates(
    client: TmdbApi, known: set[int], settings: AppSettings, today: date, limit: int | None
) -> list[int]:
    priority = await _priority_candidates(client, known, settings)
    exported = await _export_candidates(client, known | set(priority), settings, today, None)
    ids = priority + exported
    return ids[:limit] if limit is not None else ids


def _utc_today() -> date:
    return datetime.now(UTC).date()


async def run_import(
    client: TmdbApi,
    db: Database,
    settings: AppSettings,
    rec: RecommenderSettings,
    limit: int | None = None,
    on_total: OnTotal = _noop,
    on_progress: OnProgress = _noop,
) -> ImportStats:
    """İlk import. Zaten var olan veya atlanmış ID'ler yeniden çekilmez."""
    cur = db.cursor()
    ids = await _new_candidates(client, known_ids(cur), settings, _utc_today(), limit)
    on_total(len(ids))
    try:
        return await fetch_and_store(client, db, ids, settings, rec, on_progress=on_progress)
    finally:
        finalize_catalog(cur)


def _sync_start(cur: duckdb.DuckDBPyConnection, today: date, overlap_days: int) -> date:
    """Son başarılı senkron, yoksa kataloğun son güncellenme tarihi, o da yoksa bugün."""
    row = cur.execute(
        "SELECT coalesce("
        " (SELECT max(started_at) FROM jobs WHERE type = 'sync_changes' AND status = 'done'),"
        " (SELECT max(synced_at) FROM movies))"
    ).fetchone()
    last = row[0].date() if row and row[0] else today
    return min(last, today) - timedelta(days=overlap_days)


async def _changed_ids(client: TmdbApi, start: date, end: date, max_days: int) -> set[int]:
    changed: set[int] = set()
    for window_start, window_end in date_windows(start, end, max_days):
        page = 1
        while True:
            data = await client.get_changes(window_start, window_end, page)
            changed.update(int(r["id"]) for r in data.get("results", []))
            if page >= int(data.get("total_pages") or 1):
                break
            page += 1
    return changed


async def run_sync(
    client: TmdbApi,
    db: Database,
    settings: AppSettings,
    rec: RecommenderSettings,
    on_total: OnTotal = _noop,
    on_progress: OnProgress = _noop,
    today: date | None = None,
) -> ImportStats:
    """Değişen filmleri yeniler, export'taki yeni filmleri aynı filtreden geçirip ekler."""
    cur = db.cursor()
    today = today or _utc_today()
    start = _sync_start(cur, today, settings.tmdb_sync_overlap_days)
    changed = await _changed_ids(client, start, today, settings.tmdb_changes_max_days)

    ours = {int(r[0]) for r in cur.execute("SELECT tmdb_id FROM movies").fetchall()}
    refresh = sorted(changed & ours)
    new_ids = await _new_candidates(client, known_ids(cur), settings, today, None)
    on_total(len(refresh) + len(new_ids))

    def progress_after_refresh(done: int) -> None:
        on_progress(len(refresh) + done)

    try:
        stats = await fetch_and_store(
            client, db, refresh, settings, rec, apply_filter=False, on_progress=on_progress
        )
        added = await fetch_and_store(
            client, db, new_ids, settings, rec, on_progress=progress_after_refresh
        )
    finally:
        finalize_catalog(cur)
    return ImportStats(
        attempted=stats.attempted + added.attempted,
        stored=stats.stored + added.stored,
        skipped=stats.skipped + added.skipped,
        failed=stats.failed + added.failed,
    )
