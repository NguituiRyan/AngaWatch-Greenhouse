/** Device hooks: org-wide list or per-greenhouse filter (device health). */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { LIVE_REFETCH_MS } from "@/lib/live";
import type { Device } from "@/lib/types";

export function useDevices(greenhouseId?: string) {
  return useQuery({
    queryKey: ["devices", { greenhouseId: greenhouseId ?? null }],
    refetchInterval: LIVE_REFETCH_MS,
    queryFn: () =>
      api.get<Device[]>("/devices", {
        query: greenhouseId ? { greenhouse_id: greenhouseId } : undefined,
      }),
  });
}
