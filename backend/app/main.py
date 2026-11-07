"""FastAPI uygulaması: DB, migration, JobRunner yaşam döngüsü ve statik frontend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.api import health, jobs
from app.clients.ollama import LlmClient, OllamaClient
from app.config import AppSettings, get_settings
from app.db import Database, apply_migrations
from app.jobs import JobRunner
from app.jobs.demo import make_demo_job


def create_app(settings: AppSettings | None = None, llm: LlmClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    llm = llm or OllamaClient(settings.ollama_url, settings.ollama_timeout_s)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.db_path, settings.duckdb_extensions)
        db.connect()
        apply_migrations(db.cursor(), settings.migrations_dir)
        runner = JobRunner(db, {"demo": make_demo_job(settings)})
        runner.start()
        app.state.settings = settings
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
