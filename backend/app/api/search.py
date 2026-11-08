from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_db, get_rec_settings
from app.api.schemas import SearchResult
from app.config import RecommenderSettings
from app.db import Database
from app.services.search import search_movies

router = APIRouter(prefix="/api")


@router.get("/search", response_model=list[SearchResult])
def search(
    q: str,
    db: Annotated[Database, Depends(get_db)],
    rec: Annotated[RecommenderSettings, Depends(get_rec_settings)],
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> list[SearchResult]:
    return search_movies(db, q, limit, rec)
