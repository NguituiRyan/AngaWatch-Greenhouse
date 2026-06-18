/** Control hooks: actuators, command feed, and manual command dispatch. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Actuator, CommandIn, ControlCommand } from "@/lib/types";

export function useActuators(greenhouseId: string | undefined) {
  return useQuery({
    queryKey: ["actuators", greenhouseId],
    enabled: Boolean(greenhouseId),
    queryFn: () => api.get<Actuator[]>(`/greenhouses/${greenhouseId}/actuators`),
  });
}

export function useCommands(limit = 100) {
  return useQuery({
    queryKey: ["control", "commands", { limit }],
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
