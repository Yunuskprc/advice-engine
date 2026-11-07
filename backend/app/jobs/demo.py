"""Örnek iş: JobRunner'ın ilerleme raporlamasını göstermek için."""

import time

from app.config import AppSettings
from app.jobs.runner import JobContext, JobFn


def make_demo_job(settings: AppSettings) -> JobFn:
    def demo(ctx: JobContext) -> None:
        ctx.set_total(settings.demo_job_steps)
        for i in range(1, settings.demo_job_steps + 1):
            time.sleep(settings.demo_job_step_seconds)
            ctx.set_progress(i)

    return demo
