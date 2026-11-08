"""Zevk kümelerini yeniden hesaplar (JobRunner işi)."""

from app.config import RecommenderSettings
from app.jobs.runner import JobContext, JobFn
from app.services.taste import recompute_taste


def make_recompute_job(rec: RecommenderSettings) -> JobFn:
    def job(ctx: JobContext) -> None:
        ctx.set_total(1)
        recompute_taste(ctx.db, rec)
        ctx.set_progress(1)

    return job
