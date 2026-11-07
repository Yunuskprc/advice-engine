import type { HealthResponse, Job, JobSubmitted } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path}: ${res.status}`);
  return (await res.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  jobs: () => request<Job[]>("/api/jobs"),
  submitDemoJob: () => request<JobSubmitted>("/api/jobs/demo", { method: "POST" }),
};
