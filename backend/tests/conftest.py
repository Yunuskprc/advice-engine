from pathlib import Path

import pytest

from app.config import AppSettings
from app.db import Database, apply_migrations


class FakeLlm:
    def __init__(self, models: list[str] | None = None, reachable: bool = True) -> None:
        self.models = models if models is not None else ["bge-m3:latest", "qwen3:8b"]
        self.reachable = reachable

    def list_models(self, timeout: float | None = None) -> list[str]:
        if not self.reachable:
            raise ConnectionError("kapalı")
        return self.models

    def embed(self, model: str, inputs: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in inputs]

    def generate(self, model: str, prompt: str, max_tokens: int | None = None) -> str:
        return "Ankara"


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        _env_file=None,
        db_path=tmp_path / "test.duckdb",
        frontend_dist=tmp_path / "dist",
        demo_job_steps=3,
        demo_job_step_seconds=0.01,
    )


@pytest.fixture
def db(settings: AppSettings):
    d = Database(settings.db_path, settings.duckdb_extensions)
    d.connect()
    apply_migrations(d.cursor(), settings.migrations_dir)
    yield d
    d.close()
