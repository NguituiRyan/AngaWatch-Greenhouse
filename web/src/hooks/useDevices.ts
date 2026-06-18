/** Device hooks: org-wide list or per-greenhouse filter (device health). */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Device } from "@/lib/types";

export function useDevices(greenhouseId?: string) {
  return useQuery({
    queryKey: ["devices", { greenhouseId: greenhouseId ?? null }],
    refetchInterval: 60_000,
    queryFn: () =>
      api.get<Device[]>("/devices", {
        query: greenhouseId ? { greenhouse_id: greenhouseId } : undefined,
      }),
  });
}
