"""FastAPI uygulaması: DB, migration, JobRunner yaşam döngüsü ve statik frontend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.api import (
    health,
    jobs,
    library,
    movies,
    onboarding,
    recommendations,
    search,
    taste,
)
from app.clients.ollama import LlmClient, OllamaClient
from app.clients.tmdb import TmdbClient
from app.config import AppSettings, get_recommender_settings, get_settings
from app.db import Database, apply_migrations
from app.jobs import JobContext, JobFn, JobRunner
from app.jobs.demo import make_demo_job
from app.jobs.embed_movies import make_embed_job
from app.jobs.recompute_taste import make_recompute_job
from app.jobs.sync_changes import TmdbFactory, make_sync_job
from app.services.vector_index import VectorIndex


def create_app(
    settings: AppSettings | None = None,
    llm: LlmClient | None = None,
    tmdb_factory: TmdbFactory | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    llm = llm or OllamaClient(settings.ollama_url, settings.ollama_timeout_s)
    resolved = settings
    make_tmdb: TmdbFactory = tmdb_factory or (lambda: TmdbClient(resolved))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.db_path, settings.duckdb_extensions)
        db.connect()
        apply_migrations(db.cursor(), settings.migrations_dir)
        rec = get_recommender_settings()
        index = VectorIndex()
        index.refresh(db)

        def refreshing(job: JobFn) -> JobFn:
            """İş bittikten sonra bellekteki vektörleri günceller."""

            def run(ctx: JobContext) -> None:
                job(ctx)
                index.refresh(ctx.db)

            return run

        runner = JobRunner(
            db,
            {
                "demo": make_demo_job(settings),
                "sync_changes": refreshing(make_sync_job(settings, rec, make_tmdb)),
                "embed_movies": refreshing(make_embed_job(settings, rec, llm)),
                "recompute_taste": make_recompute_job(rec),
            },
        )
        runner.start()
        app.state.settings = settings
        app.state.rec = rec
        app.state.vector_index = index
        app.state.db = db
        app.state.llm = llm
        app.state.runner = runner
        try:
            yield
        finally:
            runner.stop(timeout=5)
            db.close()

    app = FastAPI(title="Film Öneri", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(movies.router)
    app.include_router(onboarding.router)
    app.include_router(library.router)
    app.include_router(search.router)
    app.include_router(taste.router)
    app.include_router(recommendations.router)
    _mount_frontend(app, settings.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """React build'ini sunar; bilinmeyen yollar index.html'e düşer (SPA)."""
    index = dist / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or not index.exists():
            raise HTTPException(status_code=404)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)
