/**
 * Manual actuator control.
 *
 * Each actuator gets command buttons appropriate to its type (vent: open/close;
 * fan/pump/valve: on/off). Pressing a button POSTs to
 * `/actuators/{id}/command` via the control service, which enqueues + executes
 * the command (the mock driver acks immediately and flips `state`).
 */

import { useActuators, useSendCommand } from "@/hooks/useControl";
import type { Actuator, ActuatorType } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { humanize, relativeTime } from "@/lib/format";

/** Command verbs offered per actuator type. */
const COMMANDS: Record<ActuatorType, string[]> = {
  vent: ["open", "close"],
  fan: ["on", "off"],
  drip_valve: ["open", "close"],
  fertigation_pump: ["on", "off"],
};

function stateTone(state: Actuator["state"]): string {
  if (state === "open" || state === "on") return "green";
  if (state === "unknown") return "slate";
  return "slate";
}

function ActuatorControl({ actuator }: { actuator: Actuator }) {
  const send = useSendCommand();
  const commands = COMMANDS[actuator.actuator_type] ?? ["on", "off"];
  const pendingCmd = send.isPending ? send.variables?.body.command : null;

  return (
    <div className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3">
        <div>
          <p className="text-sm font-medium text-slate-800">{actuator.name}</p>
          <p className="text-xs text-slate-400">
            {humanize(actuator.actuator_type)} ·{" "}
            {actuator.is_online ? "online" : "offline"}
            {actuator.last_state_change
              ? ` · ${relativeTime(actuator.last_state_change)}`
              : ""}
          </p>
        </div>
        <StatusPill label={humanize(actuator.state)} tone={stateTone(actuator.state)} />
      </div>

      <div className="flex flex-wrap gap-2 pl-0 sm:pl-2">
        {commands.map((cmd) => {
          const active = pendingCmd === cmd && send.variables?.actuatorId === actuator.id;
          return (
            <button
              key={cmd}
              type="button"
              className="btn-secondary px-3 py-1.5 text-xs"
              disabled={send.isPending || !actuator.is_online}
              onClick={() => send.mutate({ actuatorId: actuator.id, body: { command: cmd } })}
            >
              {active ? "…" : humanize(cmd)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ActuatorControls({ greenhouseId }: { greenhouseId: string }) {
  const { data, isLoading, error } = useActuators(greenhouseId);
  const send = useSendCommand();

  return (
    <Card title="Manual control">
      {isLoading ? (
        <Spinner />
      ) : error ? (
        <ErrorState error={error} />
      ) : (data ?? []).length === 0 ? (
        <EmptyState title="No actuators" hint="No controllable devices in this greenhouse." />
      ) : (
        <>
          {send.isError ? (
            <p className="mb-2 rounded bg-red-50 px-3 py-2 text-xs text-red-700">
              Command failed: {(send.error as Error).message}
            </p>
          ) : null}
          <div className="divide-y divide-slate-100">
            {data!.map((a) => (
              <ActuatorControl key={a.id} actuator={a} />
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
