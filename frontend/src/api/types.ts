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
