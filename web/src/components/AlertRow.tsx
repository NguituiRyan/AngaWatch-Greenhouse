/** A single alert row with risk badge, status, and an optional ack button. */

import type { Alert } from "@/lib/types";
import { RiskBadge, StatusPill } from "@/components/ui/Badge";
import { formatDateTime, humanize } from "@/lib/format";

function statusTone(status: Alert["status"]): string {
  switch (status) {
    case "acked":
      return "green";
    case "failed":
    case "escalated":
      return "red";
    case "sent":
    case "delivered":
      return "blue";
    default:
      return "slate";
  }
}

export function AlertRow({
  alert,
  onAck,
  acking,
}: {
  alert: Alert;
  onAck?: (id: string) => void;
  acking?: boolean;
}) {
  const canAck = onAck && alert.status !== "acked";

  return (
    <div className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <RiskBadge level={alert.level} />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-slate-800">{alert.title}</p>
          <p className="text-xs text-slate-400">
            {humanize(alert.model_type)} · {formatDateTime(alert.first_seen_at)}
            {alert.escalation_level > 0 ? ` · esc. L${alert.escalation_level}` : ""}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2 pl-9 sm:pl-0">
        <StatusPill label={humanize(alert.status)} tone={statusTone(alert.status)} />
        {canAck ? (
          <button
            type="button"
            className="btn-secondary px-3 py-1.5 text-xs"
            onClick={() => onAck?.(alert.id)}
            disabled={acking}
          >
            {acking ? "…" : "Acknowledge"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
