// backend/app/api/schemas.py ile uyumlu tutulur.

export interface DbHealth {
  ok: boolean;
  path: string;
  version: string | null;
  extensions: string[];
  migrations: string[];
  error: string | null;
}

export interface OllamaHealth {
  ok: boolean;
  url: string;
  reachable: boolean;
  embed_model: string;
  embed_model_present: boolean;
  chat_model: string;
  chat_model_present: boolean;
  error: string | null;
}

export interface HealthResponse {
  ok: boolean;
  db: DbHealth;
  ollama: OllamaHealth;
}

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface Job {
  id: number;
  type: string;
  status: JobStatus;
  progress: number;
  total: number | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobSubmitted {
  id: number;
}

export interface EmbeddingStatus {
  total: number;
  ready: number;
}

export interface TasteMovie {
  tmdb_id: number;
  title_tr: string;
  poster_path: string | null;
  membership: number;
}

export interface TasteInsights {
  rated: number;
  skipped: number;
  favorites: string[];
  avoid: string[];
  turkish_every: number;
}

export interface TasteCluster {
  id: number;
  label: string | null;
  auto_title: string;
  description: string | null;
  weight: number;
  size: number;
  top_keywords: string[];
  is_negative: boolean;
  typical: TasteMovie[];
}

export interface TasteResponse {
  clusters: TasteCluster[];
  negatives: TasteCluster[];
  computed_at: string | null;
  positive_count: number;
  min_positive: number;
  insights: TasteInsights;
}

export interface RecommendationFilters {
  year_min: number | null;
  year_max: number | null;
  runtime_min: number | null;
  runtime_max: number | null;
  origin: "all" | "domestic" | "foreign";
  genres_include: number[];
  genres_exclude: number[];
  providers: number[];
}

export interface RecommendationRequest {
  cluster_id: number | null;
  filters: RecommendationFilters;
  exploration: number;
  exclude: number[];
}

export interface RecommendedMovie {
  tmdb_id: number;
  title_tr: string;
  title_original: string;
  year: number | null;
  runtime: number | null;
  poster_path: string | null;
  vote_average: number | null;
  providers: WatchProvider[];
  explanation: string;
  score: number;
}

export interface RecommendationResponse {
  cluster_id: number | null;
  items: RecommendedMovie[];
}

export type FeedbackAction = "dismissed" | "saved" | "watched";

export interface FilterOption {
  id: number;
  name: string;
  logo_path: string | null;
}

export interface RecommendationOptions {
  genres: FilterOption[];
  providers: FilterOption[];
}

export interface WatchlistItem {
  tmdb_id: number;
  title_tr: string;
  title_original: string;
  year: number | null;
  runtime: number | null;
  poster_path: string | null;
  providers: WatchProvider[];
}

export interface TasteGroupChoice {
  id: string;
  name: string;
  films: string;
  tags: string;
  selected: boolean;
}

export interface TastePreferences {
  groups: TasteGroupChoice[];
  completed: boolean;
}

export interface AnswerRating {
  movie_id: number;
  score: number;
}

export type OnboardingStage = "warmup" | "explore" | "refine";

export interface OnboardingCard {
  tmdb_id: number;
  title_tr: string;
  title_original: string;
  year: number | null;
  poster_path: string | null;
  directors: string[];
}

export interface OnboardingBatch {
  stage: OnboardingStage;
  cards: OnboardingCard[];
}

export interface OnboardingProgress {
  rated: number;
  skipped: number;
  target: number;
  stage: OnboardingStage;
}

export interface SearchResult {
  tmdb_id: number;
  title_tr: string;
  title_original: string;
  year: number | null;
  poster_path: string | null;
  vote_average: number | null;
  my_rating: number | null;
  in_watchlist: boolean;
}

export interface SimilarMovie {
  tmdb_id: number;
  title_tr: string;
  title_original: string;
  release_date: string | null;
  poster_path: string | null;
  vote_average: number | null;
  similarity: number;
}

export interface Person {
  id: number;
  name: string;
  profile_path: string | null;
}

export interface WatchProvider {
  id: number;
  name: string;
  type: string;
  logo_path: string | null;
}

export interface MovieDetail {
  tmdb_id: number;
  title_tr: string;
  title_original: string;
  year: number | null;
  runtime: number | null;
  overview: string | null;
  vote_average: number | null;
  vote_count: number | null;
  poster_path: string | null;
  backdrop_path: string | null;
  genres: string[];
  keywords: string[];
  directors: Person[];
  cast: Person[];
  providers: WatchProvider[];
  my_rating: number | null;
  in_watchlist: boolean;
}
