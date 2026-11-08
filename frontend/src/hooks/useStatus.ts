import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const ACTIVE_POLL_MS = 500;
const IDLE_POLL_MS = 5000;
const EMBEDDING_POLL_MS = 2000;

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health });
}

export function useJobs() {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    // Çalışan iş varken sık, yoksa seyrek yenile.
    refetchInterval: (q) =>
      q.state.data?.some((j) => j.status === "queued" || j.status === "running")
        ? ACTIVE_POLL_MS
        : IDLE_POLL_MS,
  });
}

export function useEmbeddingStatus() {
  return useQuery({
    queryKey: ["embedding-status"],
    queryFn: api.embeddingStatus,
    refetchInterval: EMBEDDING_POLL_MS,
  });
}

export function useSubmitEmbedJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.submitEmbedJob,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useSubmitDemoJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.submitDemoJob,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}
