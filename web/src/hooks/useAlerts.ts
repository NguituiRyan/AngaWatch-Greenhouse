/** Alert hooks: org feed + acknowledge mutation. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Alert, AlertStatus } from "@/lib/types";

export function useAlerts(status?: AlertStatus, limit = 100) {
  return useQuery({
    queryKey: ["alerts", { status: status ?? null, limit }],
    refetchInterval: 60_000,
    queryFn: () =>
      api.get<Alert[]>("/alerts", {
        query: { status, limit },
      }),
  });
}

/** Acknowledge an alert; invalidates every alert query on success. */
export function useAckAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertId: string) => api.post<Alert>(`/alerts/${alertId}/ack`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}
