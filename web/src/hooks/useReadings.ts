/** Reading hooks: latest snapshot + historical timeseries window. */

import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "@/lib/api";
import { LIVE_REFETCH_MS } from "@/lib/live";
import type { Reading, ReadingMetric } from "@/lib/types";

/** Most recent reading for a greenhouse. 404 (no readings yet) -> null. */
export function useLatestReading(greenhouseId: string | undefined) {
  return useQuery({
    queryKey: ["readings", greenhouseId, "latest"],
    enabled: Boolean(greenhouseId),
    refetchInterval: LIVE_REFETCH_MS,
    queryFn: async () => {
      try {
        return await api.get<Reading>(`/greenhouses/${greenhouseId}/readings/latest`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
  });
}

interface ReadingsQuery {
  metric?: ReadingMetric;
  start?: string;
  end?: string;
  limit?: number;
}

/** Historical telemetry window (newest first) for charts. */
export function useReadings(greenhouseId: string | undefined, params: ReadingsQuery = {}) {
  return useQuery({
    queryKey: ["readings", greenhouseId, "window", params],
    enabled: Boolean(greenhouseId),
    queryFn: () =>
      api.get<Reading[]>(`/greenhouses/${greenhouseId}/readings`, {
        query: {
          metric: params.metric,
          start: params.start,
          end: params.end,
          limit: params.limit ?? 500,
        },
      }),
  });
}
