/** Risk hooks: current assessments per model + (premium) history. */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { LIVE_REFETCH_MS } from "@/lib/live";
import type { RiskAssessment } from "@/lib/types";

/** Latest assessment per model type for a greenhouse. */
export function useRisk(greenhouseId: string | undefined) {
  return useQuery({
    queryKey: ["risk", greenhouseId],
    enabled: Boolean(greenhouseId),
    refetchInterval: LIVE_REFETCH_MS,
    queryFn: () => api.get<RiskAssessment[]>(`/greenhouses/${greenhouseId}/risk`),
  });
}

/** Historical assessment timeline (gated by the `dashboard_history` feature). */
export function useRiskHistory(
  greenhouseId: string | undefined,
  modelType?: string,
  limit = 200,
) {
  return useQuery({
    queryKey: ["risk", greenhouseId, "history", { modelType, limit }],
    enabled: Boolean(greenhouseId),
    retry: false,
    queryFn: () =>
      api.get<RiskAssessment[]>(`/greenhouses/${greenhouseId}/risk/history`, {
        query: { model_type: modelType, limit },
      }),
  });
}
