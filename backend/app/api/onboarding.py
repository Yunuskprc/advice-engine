from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_db, get_rec_settings
from app.api.schemas import (
    OnboardingBatch,
    OnboardingProgress,
    TastePreferences,
    TastePreferencesIn,
)
from app.config import RecommenderSettings
from app.db import Database
from app.services.onboarding import (
    next_cards,
    progress,
    set_taste_preferences,
    taste_preferences,
)

router = APIRouter(prefix="/api/onboarding")


@router.get("/next", response_model=OnboardingBatch)
def next_batch(
    db: Annotated[Database, Depends(get_db)],
    rec: Annotated[RecommenderSettings, Depends(get_rec_settings)],
    exclude: Annotated[list[int] | None, Query()] = None,
    previous: int | None = None,
    count: Annotated[int | None, Query(ge=1)] = None,
) -> OnboardingBatch:
    return next_cards(db, rec, exclude or [], previous, count)


@router.get("/preferences", response_model=TastePreferences)
def get_preferences(db: Annotated[Database, Depends(get_db)]) -> TastePreferences:
    return taste_preferences(db)


@router.put("/preferences", response_model=TastePreferences)
def put_preferences(
    body: TastePreferencesIn, db: Annotated[Database, Depends(get_db)]
) -> TastePreferences:
    try:
        return set_taste_preferences(db, body.group_ids)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="Geçerli bir grup seçilmedi") from e


@router.get("/progress", response_model=OnboardingProgress)
def get_progress(
    db: Annotated[Database, Depends(get_db)],
    rec: Annotated[RecommenderSettings, Depends(get_rec_settings)],
) -> OnboardingProgress:
    return progress(db, rec)
