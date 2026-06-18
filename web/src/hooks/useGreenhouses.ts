/** Greenhouse hooks. */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Greenhouse } from "@/lib/types";

export function useGreenhouses(farmId?: string) {
  return useQuery({
    queryKey: ["greenhouses", { farmId: farmId ?? null }],
    queryFn: () =>
      api.get<Greenhouse[]>("/greenhouses", {
        query: farmId ? { farm_id: farmId } : undefined,
      }),
  });
}

export function useGreenhouse(greenhouseId: string | undefined) {
  return useQuery({
    queryKey: ["greenhouses", greenhouseId],
    queryFn: () => api.get<Greenhouse>(`/greenhouses/${greenhouseId}`),
    enabled: Boolean(greenhouseId),
  });
}
