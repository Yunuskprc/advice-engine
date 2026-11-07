from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_app_settings, get_db, get_llm
from app.api.schemas import HealthResponse
from app.clients.ollama import LlmClient
from app.config import AppSettings
from app.db import Database
from app.services.health import check_health

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health(
    db: Annotated[Database, Depends(get_db)],
    llm: Annotated[LlmClient, Depends(get_llm)],
    settings: Annotated[AppSettings, Depends(get_app_settings)],
) -> HealthResponse:
    return check_health(db, llm, settings)
