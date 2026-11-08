"""Bekleyen filmlerin embedding'lerini üretir (JobRunner işi)."""

from app.clients.ollama import LlmClient
from app.config import AppSettings, RecommenderSettings
from app.jobs.runner import JobContext, JobFn
from app.services.embedding import embed_pending


def make_embed_job(settings: AppSettings, rec: RecommenderSettings, llm: LlmClient) -> JobFn:
    def embed_movies(ctx: JobContext) -> None:
        embed_pending(ctx.db, llm, settings, rec, ctx.set_total, ctx.set_progress)

    return embed_movies
