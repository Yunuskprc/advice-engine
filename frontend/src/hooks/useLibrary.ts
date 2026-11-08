import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

const TASTE_POLL_MS = 5000;

export function useTaste() {
  return useQuery({
    queryKey: ["taste"],
    queryFn: api.taste,
    refetchInterval: TASTE_POLL_MS,
  });
}

export function useRecomputeTaste() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.submitRecompute,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

const TASTE_PREFERENCES_KEY = ["taste-preferences"];

export function useTastePreferences() {
  return useQuery({ queryKey: TASTE_PREFERENCES_KEY, queryFn: api.tastePreferences });
}

export function useSaveTastePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.saveTastePreferences,
    onSuccess: (data) => qc.setQueryData(TASTE_PREFERENCES_KEY, data),
  });
}

export function useProgress() {
  return useQuery({ queryKey: ["progress"], queryFn: api.progress });
}

function useInvalidateMovie() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["search"] });
    void qc.invalidateQueries({ queryKey: ["movie"] });
    void qc.invalidateQueries({ queryKey: ["progress"] });
  };
}

/** Arama ve film detay ekranlarındaki puanlama. Aynı yıldıza basmak puanı siler. */
export function useRateMovie() {
  const invalidate = useInvalidateMovie();
  return useMutation({
    mutationFn: ({ id, score }: { id: number; score: number | null }) =>
      score === null ? api.unrate(id) : api.rate(id, score),
    onSuccess: invalidate,
  });
}

export function useToggleWatchlist() {
  const invalidate = useInvalidateMovie();
  return useMutation({
    mutationFn: ({ id, inList }: { id: number; inList: boolean }) =>
      inList ? api.removeFromWatchlist(id) : api.addToWatchlist(id),
    onSuccess: invalidate,
  });
}
