/** Weather hook: latest observation + upcoming forecasts for a farm. */

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { FarmWeather } from "@/lib/types";

export function useFarmWeather(farmId: string | undefined, forecastLimit = 24) {
  return useQuery({
    queryKey: ["weather", farmId, { forecastLimit }],
    enabled: Boolean(farmId),
    refetchInterval: 10 * 60 * 1000,
    queryFn: () =>
      api.get<FarmWeather>(`/farms/${farmId}/weather`, {
        query: { forecast_limit: forecastLimit },
      }),
  });
}
