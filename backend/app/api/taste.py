from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_db, get_rec_settings
from app.api.schemas import TasteResponse
from app.config import RecommenderSettings
from app.db import Database
from app.services.taste import get_taste

router = APIRouter(prefix="/api")


@router.get("/taste", response_model=TasteResponse)
def taste(
    db: Annotated[Database, Depends(get_db)],
    rec: Annotated[RecommenderSettings, Depends(get_rec_settings)],
) -> TasteResponse:
    return get_taste(db, rec)
