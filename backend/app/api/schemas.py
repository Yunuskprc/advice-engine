"""API şemaları. Frontend tipleri (frontend/src/api/types.ts) bunlarla uyumlu tutulur."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class SimilarMovie(BaseModel):
    tmdb_id: int
    title_tr: str
    title_original: str
    release_date: date | None
    poster_path: str | None
    vote_average: float | None
    similarity: float


class EmbeddingStatus(BaseModel):
    total: int
    ready: int


OnboardingStage = Literal["warmup", "explore", "refine"]


class OnboardingCard(BaseModel):
    tmdb_id: int
    title_tr: str
    title_original: str
    year: int | None
    poster_path: str | None
    directors: list[str]


class OnboardingBatch(BaseModel):
    stage: OnboardingStage
    cards: list[OnboardingCard]


class TasteGroupChoice(BaseModel):
    id: str
    name: str
    films: str
    tags: str
    selected: bool


class TastePreferences(BaseModel):
    groups: list[TasteGroupChoice]
    completed: bool


class TastePreferencesIn(BaseModel):
    group_ids: list[str] = Field(min_length=1)


class AnswerRating(BaseModel):
    movie_id: int
    score: int = Field(ge=1, le=5)


class OnboardingAnswers(BaseModel):
    ratings: list[AnswerRating] = []
    skips: list[int] = []


class AnswerIds(BaseModel):
    movie_ids: list[int]


class OnboardingProgress(BaseModel):
    rated: int
    skipped: int
    target: int
    stage: OnboardingStage


class TasteMovie(BaseModel):
    tmdb_id: int
    title_tr: str
    poster_path: str | None
    membership: float


class TasteInsights(BaseModel):
    rated: int
    skipped: int
    favorites: list[str]
    avoid: list[str]
    turkish_every: int


class TasteCluster(BaseModel):
    id: int
    label: str | None
    auto_title: str
    description: str | None
    weight: float
    size: int
    top_keywords: list[str]
    is_negative: bool
    typical: list[TasteMovie]


class TasteResponse(BaseModel):
    clusters: list[TasteCluster]
    negatives: list[TasteCluster]
    computed_at: datetime | None
    positive_count: int
    min_positive: int
    insights: TasteInsights


class RecommendationFilters(BaseModel):
    year_min: int | None = None
    year_max: int | None = None
    runtime_min: int | None = None
    runtime_max: int | None = None
    origin: Literal["all", "domestic", "foreign"] = "all"
    genres_include: list[int] = []
    genres_exclude: list[int] = []
    providers: list[int] = []


class RecommendationRequest(BaseModel):
    cluster_id: int | None = None  # None: Beni şaşırt
    filters: RecommendationFilters = RecommendationFilters()
    exploration: float = Field(default=0.0, ge=0.0, le=1.0)
    exclude: list[int] = []


class RecommendedMovie(BaseModel):
    tmdb_id: int
    title_tr: str
    title_original: str
    year: int | None
    runtime: int | None
    poster_path: str | None
    vote_average: float | None
    providers: list["ProviderOut"]
    explanation: str
    score: float


class RecommendationResponse(BaseModel):
    cluster_id: int | None
    items: list[RecommendedMovie]


class RecommendationFeedback(BaseModel):
    action: Literal["dismissed", "saved", "watched"]
    cluster_id: int | None = None


class FilterOption(BaseModel):
    id: int
    name: str
    logo_path: str | None = None


class RecommendationOptions(BaseModel):
    genres: list[FilterOption]
    providers: list[FilterOption]


class WatchlistItem(BaseModel):
    tmdb_id: int
    title_tr: str
    title_original: str
    year: int | None
    runtime: int | None
    poster_path: str | None
    providers: list["ProviderOut"]


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=5)


class SearchResult(BaseModel):
    tmdb_id: int
    title_tr: str
    title_original: str
    year: int | None
    poster_path: str | None
    vote_average: float | None
    my_rating: int | None
    in_watchlist: bool


class PersonOut(BaseModel):
    id: int
    name: str
    profile_path: str | None


class ProviderOut(BaseModel):
    id: int
    name: str
    type: str
    logo_path: str | None


class MovieDetail(BaseModel):
    tmdb_id: int
    title_tr: str
    title_original: str
    year: int | None
    runtime: int | None
    overview: str | None
    vote_average: float | None
    vote_count: int | None
    poster_path: str | None
    backdrop_path: str | None
    genres: list[str]
    keywords: list[str]
    directors: list[PersonOut]
    cast: list[PersonOut]
    providers: list[ProviderOut]
    my_rating: int | None
    in_watchlist: bool
