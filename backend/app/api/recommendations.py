from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import get_db, get_rec_settings, get_vector_index
from app.api.schemas import (
    RecommendationFeedback,
    RecommendationOptions,
    RecommendationRequest,
    RecommendationResponse,
    WatchlistItem,
)
from app.config import RecommenderSettings
from app.db import Database
from app.services import library
from app.services.recommendations import ClusterNotFoundError, filter_options, recommend
from app.services.similar import MovieNotFoundError
from app.services.vector_index import VectorIndex

router = APIRouter(prefix="/api")

Db = Annotated[Database, Depends(get_db)]
Rec = Annotated[RecommenderSettings, Depends(get_rec_settings)]
NO_CONTENT = 204


@router.post("/recommendations", response_model=RecommendationResponse)
def recommendations(
    body: RecommendationRequest,
    db: Db,
    rec: Rec,
    index: Annotated[VectorIndex, Depends(get_vector_index)],
) -> RecommendationResponse:
    try:
        return recommend(db, rec, body, index)
    except ClusterNotFoundError as e:
        raise HTTPException(status_code=404, detail="Küme bulunamadı") from e


@router.get("/recommendations/options", response_model=RecommendationOptions)
def options(db: Db, rec: Rec) -> RecommendationOptions:
    return filter_options(db, rec)


@router.post("/recommendations/{tmdb_id}/feedback", status_code=NO_CONTENT, response_class=Response)
def feedback(tmdb_id: int, body: RecommendationFeedback, db: Db) -> None:
    try:
        library.add_feedback(db, tmdb_id, body.action, body.cluster_id)
    except MovieNotFoundError as e:
        raise HTTPException(status_code=404, detail="Film bulunamadı") from e


@router.delete(
    "/recommendations/{tmdb_id}/feedback/{action}",
    status_code=NO_CONTENT,
    response_class=Response,
)
def undo_feedback(tmdb_id: int, action: Literal["dismissed", "saved", "watched"], db: Db) -> None:
    library.remove_feedback(db, tmdb_id, action)


@router.get("/watchlist", response_model=list[WatchlistItem])
def watchlist(db: Db) -> list[WatchlistItem]:
    return library.list_watchlist(db)
