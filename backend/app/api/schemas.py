"""API şemaları. Frontend tipleri (frontend/src/api/types.ts) bunlarla uyumlu tutulur."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DbHealth(BaseModel):
    ok: bool
    path: str
    version: str | None = None
    extensions: list[str] = []
    migrations: list[str] = []
    error: str | None = None


class OllamaHealth(BaseModel):
    ok: bool
    url: str
    reachable: bool = False
    embed_model: str
    embed_model_present: bool = False
    chat_model: str
    chat_model_present: bool = False
    error: str | None = None


class HealthResponse(BaseModel):
    ok: bool
    db: DbHealth
    ollama: OllamaHealth


JobStatus = Literal["queued", "running", "done", "failed"]


class Job(BaseModel):
    id: int
    type: str
    status: JobStatus
    progress: int
    total: int | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobSubmitted(BaseModel):
    id: int
