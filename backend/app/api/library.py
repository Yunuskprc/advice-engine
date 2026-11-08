from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import get_db, get_rec_settings, get_runner
from app.api.schemas import AnswerIds, OnboardingAnswers, RatingIn
from app.config import RecommenderSettings
from app.db import Database
from app.jobs import JobRunner
from app.services import library
from app.services.similar import MovieNotFoundError
from app.services.taste import ratings_since_last_recompute

router = APIRouter(prefix="/api")

Db = Annotated[Database, Depends(get_db)]
NO_CONTENT = 204


def _not_found(e: MovieNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail="Film bulunamadı")


@router.put("/ratings/{tmdb_id}", status_code=NO_CONTENT, response_class=Response)
def put_rating(
    tmdb_id: int,
    body: RatingIn,
    db: Db,
    runner: Annotated[JobRunner, Depends(get_runner)],
    rec: Annotated[RecommenderSettings, Depends(get_rec_settings)],
) -> None:
    try:
        library.set_rating(db, tmdb_id, body.score)
    except MovieNotFoundError as e:
        raise _not_found(e) from e
    if ratings_since_last_recompute(db.cursor()) >= rec.recompute_every_n_ratings:
        runner.submit("recompute_taste")


@router.post("/onboarding/answers", status_code=NO_CONTENT, response_class=Response)
def post_answers(
    body: OnboardingAnswers,
    db: Db,
    runner: Annotated[JobRunner, Depends(get_runner)],
    rec: Annotated[RecommenderSettings, Depends(get_rec_settings)],
) -> None:
    library.save_answers(db, [(r.movie_id, r.score) for r in body.ratings], body.skips)
    if ratings_since_last_recompute(db.cursor()) >= rec.recompute_every_n_ratings:
        runner.submit("recompute_taste")


@router.post("/onboarding/answers/remove", status_code=NO_CONTENT, response_class=Response)
def remove_answers(body: AnswerIds, db: Db) -> None:
    library.remove_answers(db, body.movie_ids)


@router.delete("/ratings/{tmdb_id}", status_code=NO_CONTENT, response_class=Response)
def del_rating(tmdb_id: int, db: Db) -> None:
    library.delete_rating(db, tmdb_id)


@router.put("/onboarding/skips/{tmdb_id}", status_code=NO_CONTENT, response_class=Response)
def put_skip(tmdb_id: int, db: Db) -> None:
    try:
        library.add_skip(db, tmdb_id)
    except MovieNotFoundError as e:
        raise _not_found(e) from e


@router.delete("/onboarding/skips/{tmdb_id}", status_code=NO_CONTENT, response_class=Response)
def del_skip(tmdb_id: int, db: Db) -> None:
    library.delete_skip(db, tmdb_id)


@router.put("/watchlist/{tmdb_id}", status_code=NO_CONTENT, response_class=Response)
def put_watchlist(tmdb_id: int, db: Db) -> None:
    try:
        library.add_to_watchlist(db, tmdb_id)
    except MovieNotFoundError as e:
        raise _not_found(e) from e


@router.delete("/watchlist/{tmdb_id}", status_code=NO_CONTENT, response_class=Response)
def del_watchlist(tmdb_id: int, db: Db) -> None:
    library.remove_from_watchlist(db, tmdb_id)
