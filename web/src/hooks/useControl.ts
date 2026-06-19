/** Control hooks: actuators, command feed, and manual command dispatch. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { LIVE_REFETCH_MS } from "@/lib/live";
import type { Actuator, CommandIn, ControlCommand } from "@/lib/types";

export function useActuators(greenhouseId: string | undefined) {
  return useQuery({
    queryKey: ["actuators", greenhouseId],
    enabled: Boolean(greenhouseId),
    // Poll so a device's confirmed relay state (via its MQTT ack) shows up live.
    refetchInterval: LIVE_REFETCH_MS,
    queryFn: () => api.get<Actuator[]>(`/greenhouses/${greenhouseId}/actuators`),
  });
}

export function useCommands(limit = 100) {
  return useQuery({
    queryKey: ["control", "commands", { limit }],
    refetchInterval: LIVE_REFETCH_MS,
    queryFn: () => api.get<ControlCommand[]>("/control/commands", { query: { limit } }),
  });
}

interface SendCommandArgs {
  actuatorId: string;
  body: CommandIn;
}

/** POST a manual actuator command; refreshes actuator state + command feed. */
export function useSendCommand() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ actuatorId, body }: SendCommandArgs) =>
      api.post<ControlCommand>(`/actuators/${actuatorId}/command`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["actuators"] });
      void qc.invalidateQueries({ queryKey: ["control", "commands"] });
    },
  });
}
