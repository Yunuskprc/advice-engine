import asyncio
import copy
import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from app.config import RecommenderSettings
from app.jobs import JobRunner
from app.jobs.sync_changes import make_sync_job
from app.services.catalog import date_windows, run_import, run_sync, select_candidates
from app.services.movie_parser import parse_movie


def raw_movie(tmdb_id: int, **over) -> dict:
    base = {
        "id": tmdb_id,
        "title": f"Film {tmdb_id}",
        "original_title": f"Original {tmdb_id}",
        "original_language": "en",
        "overview": "Türkçe özet",
        "release_date": "2010-07-16",
        "runtime": 120,
        "vote_average": 8.0,
        "vote_count": 1000,
        "popularity": 50.0,
        "poster_path": "/p.jpg",
        "backdrop_path": "",
        "genres": [{"id": 18, "name": "Dram"}],
        "keywords": {"keywords": [{"id": 1, "name": "time loop"}]},
        "credits": {
            "crew": [{"id": 100, "name": "Yönetmen", "job": "Director"}],
            "cast": [{"id": 200 + i, "name": f"Oyuncu {i}", "order": i} for i in range(7)],
        },
        "translations": {
            "translations": [
                {"iso_639_1": "en", "iso_3166_1": "GB", "data": {"title": "x", "overview": "GB"}},
                {"iso_639_1": "en", "iso_3166_1": "US", "data": {"title": "y", "overview": "US"}},
            ]
        },
        "watch/providers": {
            "results": {
                "TR": {"flatrate": [{"provider_id": 8, "provider_name": "Netflix"}]},
                "US": {"flatrate": [{"provider_id": 9, "provider_name": "Hulu"}]},
            }
        },
    }
    return {**base, **over}


class FakeTmdb:
    def __init__(self, movies: list[dict], popularity: float = 50.0) -> None:
        self.movies = {m["id"]: m for m in movies}
        self.popularity = popularity
        self.fetched: list[int] = []
        self.changes: list[int] = []
        self.discovered: list[int] = []

    async def get_movie(self, tmdb_id: int):
        self.fetched.append(tmdb_id)
        return copy.deepcopy(self.movies.get(tmdb_id))

    async def discover_language(self, language: str, page: int) -> dict:
        return {"results": [{"id": i} for i in self.discovered], "total_pages": 1}

    async def get_changes(self, start: date, end: date, page: int) -> dict:
        return {"results": [{"id": i} for i in self.changes], "total_pages": 1}

    async def download_export(self, dest_dir: Path, today: date) -> Path:
        path = dest_dir / "export.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for i in self.movies:
                f.write(json.dumps({"id": i, "adult": False, "popularity": self.popularity}) + "\n")
        return path


@pytest.fixture
def rec() -> RecommenderSettings:
    return RecommenderSettings(_env_file=None)


def _count(db, table: str) -> int:
    return db.cursor().execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_parse_turkish_film_and_cast_limit(settings, rec) -> None:
    raw = raw_movie(1, original_language="tr", original_title="Kış Uykusu", title="Winter Sleep")
    m = parse_movie(raw, settings, rec.feat_cast_top_n)
    assert m.title_tr == "Kış Uykusu"
    assert m.overview_tr == "Türkçe özet"
    assert m.overview_en == "US"
    assert m.backdrop_path is None
    assert sum(p.role == "cast" for p in m.people) == rec.feat_cast_top_n
    assert [p.name for p in m.providers] == ["Netflix"]


def test_select_candidates_filters_and_sorts() -> None:
    rows = [
        {"id": 1, "popularity": 5},
        {"id": 2, "popularity": 9},
        {"id": 3, "popularity": 0.1},
        {"id": 4, "popularity": 9, "adult": True},
        {"id": 5, "popularity": 7},
    ]
    assert select_candidates(rows, {5}, 1.0) == [2, 1]
    assert select_candidates(rows, set(), 1.0, limit=1) == [2]


def test_date_windows_respect_max_days() -> None:
    windows = date_windows(date(2026, 1, 1), date(2026, 1, 30), 14)
    assert windows[0] == (date(2026, 1, 1), date(2026, 1, 14))
    assert windows[-1][1] == date(2026, 1, 30)
    assert len(windows) == 3


def test_import_filters_writes_and_resumes(db, settings, rec) -> None:
    fake = FakeTmdb(
        [raw_movie(1), raw_movie(2), raw_movie(3, vote_count=5), raw_movie(4, runtime=10)]
    )

    first = asyncio.run(run_import(fake, db, settings, rec, limit=3))
    assert first.attempted == 3
    assert _count(db, "movies") + _count(db, "skipped_tmdb_ids") == 3

    fake.fetched.clear()
    second = asyncio.run(run_import(fake, db, settings, rec))
    assert fake.fetched == [4]  # sadece kalan ID çekildi
    assert second.attempted == 1

    assert _count(db, "movies") == 2
    assert _count(db, "skipped_tmdb_ids") == 2
    assert _count(db, "movie_genre") == 2
    assert db.cursor().execute("SELECT df FROM keywords WHERE id = 1").fetchone() == (2,)

    fake.fetched.clear()
    asyncio.run(run_import(fake, db, settings, rec))
    assert fake.fetched == []


def test_fts_finds_title(db, settings, rec) -> None:
    fake = FakeTmdb([raw_movie(1, original_language="tr", original_title="Esaretin Bedeli")])
    asyncio.run(run_import(fake, db, settings, rec))
    row = (
        db.cursor()
        .execute(
            "SELECT tmdb_id FROM (SELECT tmdb_id,"
            " fts_main_movies.match_bm25(tmdb_id, 'esaretin') AS s FROM movies) WHERE s IS NOT NULL"
        )
        .fetchone()
    )
    assert row == (1,)


def test_sync_refreshes_changed_and_marks_stale(db, settings, rec) -> None:
    fake = FakeTmdb([raw_movie(1), raw_movie(2)])
    asyncio.run(run_import(fake, db, settings, rec))
    cur = db.cursor()
    cur.execute("UPDATE movies SET embedding_stale = FALSE")
    embedding = [0.5] * settings.embedding_dim
    cur.execute("UPDATE movies SET embedding = ?::FLOAT[1024] WHERE tmdb_id = 2", [embedding])

    # 1'in özeti değişti, 2 sadece puan aldı; 3 yepyeni film.
    fake.movies[1] = raw_movie(1, overview="Yeni özet")
    fake.movies[2] = raw_movie(2, vote_count=2000)
    fake.movies[3] = raw_movie(3)
    fake.changes = [1, 2, 999]
    stats = asyncio.run(run_sync(fake, db, settings, rec, today=date(2026, 11, 8)))

    assert stats.stored == 3
    assert 999 not in fake.fetched
    rows = dict(cur.execute("SELECT tmdb_id, embedding_stale FROM movies").fetchall())
    assert rows == {1: True, 2: False, 3: True}
    row = cur.execute("SELECT vote_count, embedding IS NOT NULL FROM movies WHERE tmdb_id = 2")
    assert row.fetchone() == (2000, True)
    assert _count(db, "movie_genre") == 3  # kopya ilişki yok


class _FakeFactory:
    def __init__(self, fake: FakeTmdb) -> None:
        self.fake = fake

    async def __aenter__(self) -> FakeTmdb:
        return self.fake

    async def __aexit__(self, *exc) -> None:
        return None


def test_sync_job_runs_in_runner(db, settings, rec) -> None:
    fake = FakeTmdb([raw_movie(1)])
    runner = JobRunner(
        db, {"sync_changes": make_sync_job(settings, rec, lambda: _FakeFactory(fake))}
    )
    runner.start()
    job_id = runner.submit("sync_changes")
    runner.stop(timeout=10)
    row = db.cursor().execute("SELECT status, error FROM jobs WHERE id = ?", [job_id]).fetchone()
    assert row == ("done", None)
    assert _count(db, "movies") == 1


def test_priority_language_found_below_popularity_threshold(db, settings, rec) -> None:
    fake = FakeTmdb([raw_movie(1, original_language="tr")], popularity=0.01)
    fake.discovered = [1]
    stats = asyncio.run(run_import(fake, db, settings, rec))
    assert stats.stored == 1
    assert _count(db, "movies") == 1
