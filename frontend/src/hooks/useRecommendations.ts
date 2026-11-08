import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { FeedbackAction, RecommendationRequest } from "../api/types";

export function useRecommendations(request: RecommendationRequest, nonce: number) {
  return useQuery({
    queryKey: ["recommendations", request, nonce],
    queryFn: () => api.recommendations(request),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    retry: false,
  });
}

export function useRecommendationOptions() {
  return useQuery({
    queryKey: ["recommendation-options"],
    queryFn: api.recommendationOptions,
    staleTime: Infinity,
  });
}

export function useFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      action,
      clusterId,
    }: {
      id: number;
      action: FeedbackAction;
      clusterId: number | null;
    }) => api.feedback(id, action, clusterId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
}

export function useWatchlist() {
  return useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist });
}

export function useMarkWatched() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, score }: { id: number; score: number }) => {
      await api.rate(id, score);
      await api.feedback(id, "watched", null);
      await api.removeFromWatchlist(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchlist"] });
      void qc.invalidateQueries({ queryKey: ["progress"] });
    },
  });
}
