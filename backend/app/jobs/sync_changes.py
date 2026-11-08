"""Günlük TMDB senkronu (JobRunner işi)."""

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from app.clients.tmdb import TmdbApi
from app.config import AppSettings, RecommenderSettings
from app.jobs.runner import JobContext, JobFn
from app.services.catalog import ImportStats, run_sync

TmdbFactory = Callable[[], AbstractAsyncContextManager[TmdbApi]]


def make_sync_job(
    settings: AppSettings, rec: RecommenderSettings, tmdb_factory: TmdbFactory
) -> JobFn:
    def sync_changes(ctx: JobContext) -> None:
        def on_progress(done: int) -> None:
            if done % settings.tmdb_batch_size == 0:
                ctx.set_progress(done)

        async def run() -> ImportStats:
            async with tmdb_factory() as client:
                return await run_sync(client, ctx.db, settings, rec, ctx.set_total, on_progress)

        stats = asyncio.run(run())
        ctx.set_progress(stats.attempted)

    return sync_changes
