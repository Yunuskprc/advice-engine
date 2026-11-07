import threading
import time

from app.db import Database
from app.jobs import JobContext, JobRunner


def _wait_status(db: Database, job_id: int, status: str, timeout: float = 5.0) -> tuple:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = (
            db.cursor()
            .execute("SELECT status, progress, total, error FROM jobs WHERE id = ?", [job_id])
            .fetchone()
        )
        if row and row[0] == status:
            return row
        time.sleep(0.02)
    raise AssertionError(f"İş {job_id} '{status}' durumuna gelmedi: {row}")


def test_job_runs_and_reports_progress(db: Database) -> None:
    def job(ctx: JobContext) -> None:
        ctx.set_total(3)
        for i in range(1, 4):
            ctx.set_progress(i)

    runner = JobRunner(db, {"t": job})
    runner.start()
    try:
        row = _wait_status(db, runner.submit("t"), "done")
        assert row[1:3] == (3, 3)
    finally:
        runner.stop(timeout=5)


def test_failed_job_records_error(db: Database) -> None:
    def boom(ctx: JobContext) -> None:
        raise ValueError("patladı")

    runner = JobRunner(db, {"boom": boom})
    runner.start()
    try:
        row = _wait_status(db, runner.submit("boom"), "failed")
        assert "patladı" in row[3]
    finally:
        runner.stop(timeout=5)


def test_same_type_not_queued_twice(db: Database) -> None:
    gate = threading.Event()
    runner = JobRunner(db, {"slow": lambda ctx: gate.wait(5), "x": lambda ctx: None})
    runner.start()
    try:
        first = runner.submit("slow")
        _wait_status(db, first, "running")
        second = runner.submit("slow")  # kuyruğa girer
        assert runner.submit("slow") == second  # tekrar eklenmez
        gate.set()
        _wait_status(db, second, "done")
    finally:
        gate.set()
        runner.stop(timeout=5)
