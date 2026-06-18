/** Farm hooks. */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Farm } from "@/lib/types";

export function useFarms() {
  return useQuery({
    queryKey: ["farms"],
    queryFn: () => api.get<Farm[]>("/farms"),
  });
}

export function useFarm(farmId: string | undefined) {
  return useQuery({
    queryKey: ["farms", farmId],
    queryFn: () => api.get<Farm>(`/farms/${farmId}`),
    enabled: Boolean(farmId),
  });
}
