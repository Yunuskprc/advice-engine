from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_db, get_rec_settings
from app.api.schemas import EmbeddingStatus, MovieDetail, SimilarMovie
from app.config import RecommenderSettings
from app.db import Database
from app.services.embedding import embedding_status
from app.services.movies import movie_detail
from app.services.similar import EmbeddingMissingError, MovieNotFoundError, similar_movies

router = APIRouter(prefix="/api")


@router.get("/movies/{tmdb_id}", response_model=MovieDetail)
def detail(tmdb_id: int, db: Annotated[Database, Depends(get_db)]) -> MovieDetail:
    try:
        return movie_detail(db, tmdb_id)
    except MovieNotFoundError as e:
        raise HTTPException(status_code=404, detail="Film bulunamadı") from e


@router.get("/movies/{tmdb_id}/similar", response_model=list[SimilarMovie])
def similar(
    tmdb_id: int,
    db: Annotated[Database, Depends(get_db)],
    rec: Annotated[RecommenderSettings, Depends(get_rec_settings)],
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> list[SimilarMovie]:
    capped = min(limit or rec.similar_default_limit, rec.similar_max_limit)
    try:
        return similar_movies(db, tmdb_id, capped)
    except MovieNotFoundError as e:
        raise HTTPException(status_code=404, detail="Film bulunamadı") from e
    except EmbeddingMissingError as e:
        raise HTTPException(status_code=409, detail="Bu filmin embedding'i henüz yok") from e


@router.get("/embeddings/status", response_model=EmbeddingStatus)
def status(db: Annotated[Database, Depends(get_db)]) -> EmbeddingStatus:
    total, ready = embedding_status(db.cursor())
    return EmbeddingStatus(total=total, ready=ready)
