"""Job sorguları."""

from app.api.schemas import Job
from app.db import Database


def list_jobs(db: Database, limit: int) -> list[Job]:
    cur = db.cursor()
    cur.execute(
        "SELECT id, type, status, progress, total, error, created_at, started_at, finished_at"
        " FROM jobs ORDER BY id DESC LIMIT ?",
        [limit],
    )
    names = [d[0] for d in cur.description]
    return [Job(**dict(zip(names, r, strict=True))) for r in cur.fetchall()]
