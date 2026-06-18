/** Recommendation hooks: list + agronomist override. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Recommendation } from "@/lib/types";

export function useRecommendations(limit = 100) {
  return useQuery({
    queryKey: ["recommendations", { limit }],
    queryFn: () => api.get<Recommendation[]>("/recommendations", { query: { limit } }),
  });
}

interface OverrideArgs {
  recommendationId: string;
  message: string;
}

/** Agronomist / coop_admin override of a recommendation's plain-language action. */
export function useOverrideRecommendation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ recommendationId, message }: OverrideArgs) =>
      api.post<Recommendation>(`/recommendations/${recommendationId}/override`, { message }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });
}
