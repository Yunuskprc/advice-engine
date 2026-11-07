from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_db, get_runner
from app.api.schemas import Job, JobSubmitted
from app.db import Database
from app.jobs import JobRunner
from app.services.jobs import list_jobs

router = APIRouter(prefix="/api/jobs")


@router.get("", response_model=list[Job])
def jobs(
    db: Annotated[Database, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> list[Job]:
    return list_jobs(db, limit)


@router.post("/demo", response_model=JobSubmitted)
def submit_demo(runner: Annotated[JobRunner, Depends(get_runner)]) -> JobSubmitted:
    return JobSubmitted(id=runner.submit("demo"))
