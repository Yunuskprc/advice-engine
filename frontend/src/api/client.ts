import type {
  EmbeddingStatus,
  AnswerRating,
  FeedbackAction,
  HealthResponse,
  Job,
  JobSubmitted,
  MovieDetail,
  OnboardingBatch,
  OnboardingProgress,
  RecommendationOptions,
  RecommendationRequest,
  RecommendationResponse,
  SearchResult,
  SimilarMovie,
  TastePreferences,
  TasteResponse,
  WatchlistItem,
} from "./types";

const NO_CONTENT = 204;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path}: ${res.status}`);
  if (res.status === NO_CONTENT) return undefined as T;
  return (await res.json()) as T;
}

const put = (path: string, body?: unknown) =>
  request<void>(path, {
    method: "PUT",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
const del = (path: string) => request<void>(path, { method: "DELETE" });

function nextCardsPath(exclude: number[], previous: number | null): string {
  const params = new URLSearchParams();
  exclude.forEach((id) => params.append("exclude", String(id)));
  if (previous !== null) params.set("previous", String(previous));
  return `/api/onboarding/next?${params.toString()}`;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  jobs: () => request<Job[]>("/api/jobs"),
  submitDemoJob: () => request<JobSubmitted>("/api/jobs/demo", { method: "POST" }),
  embeddingStatus: () => request<EmbeddingStatus>("/api/embeddings/status"),
  submitEmbedJob: () => request<JobSubmitted>("/api/jobs/embed-movies", { method: "POST" }),
  recommendations: (body: RecommendationRequest) =>
    request<RecommendationResponse>("/api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  recommendationOptions: () => request<RecommendationOptions>("/api/recommendations/options"),
  feedback: (id: number, action: FeedbackAction, clusterId: number | null) =>
    request<void>(`/api/recommendations/${id}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, cluster_id: clusterId }),
    }),
  watchlist: () => request<WatchlistItem[]>("/api/watchlist"),
  taste: () => request<TasteResponse>("/api/taste"),
  submitRecompute: () => request<JobSubmitted>("/api/jobs/recompute-taste", { method: "POST" }),
  nextCards: (exclude: number[], previous: number | null) =>
    request<OnboardingBatch>(nextCardsPath(exclude, previous)),
  progress: () => request<OnboardingProgress>("/api/onboarding/progress"),
  tastePreferences: () => request<TastePreferences>("/api/onboarding/preferences"),
  saveTastePreferences: (groupIds: string[]) =>
    request<TastePreferences>("/api/onboarding/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_ids: groupIds }),
    }),
  saveAnswers: (ratings: AnswerRating[], skips: number[]) =>
    request<void>("/api/onboarding/answers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ratings, skips }),
    }),
  removeAnswers: (movieIds: number[]) =>
    request<void>("/api/onboarding/answers/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ movie_ids: movieIds }),
    }),
  undoFeedback: (id: number, action: FeedbackAction) =>
    del(`/api/recommendations/${id}/feedback/${action}`),
  rate: (id: number, score: number) => put(`/api/ratings/${id}`, { score }),
  unrate: (id: number) => del(`/api/ratings/${id}`),
  skip: (id: number) => put(`/api/onboarding/skips/${id}`),
  unskip: (id: number) => del(`/api/onboarding/skips/${id}`),
  addToWatchlist: (id: number) => put(`/api/watchlist/${id}`),
  removeFromWatchlist: (id: number) => del(`/api/watchlist/${id}`),
  search: (q: string) => request<SearchResult[]>(`/api/search?q=${encodeURIComponent(q)}`),
  movie: (id: number) => request<MovieDetail>(`/api/movies/${id}`),
  similar: (id: number) => request<SimilarMovie[]>(`/api/movies/${id}/similar`),
};
