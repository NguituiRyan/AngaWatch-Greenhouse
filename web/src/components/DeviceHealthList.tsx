/** Compact device-health list: battery, last-seen, RSSI, status. */

import type { Device } from "@/lib/types";
import { StatusPill } from "@/components/ui/Badge";
import { metricValue, relativeTime } from "@/lib/format";

function statusTone(status: Device["status"]): string {
  return status === "active" ? "green" : status === "fault" ? "red" : "slate";
}

/** Heuristic battery tone: low < 3.4V on a typical Li-ion node. */
function batteryTone(v: number | null): string {
  if (v === null) return "slate";
  if (v < 3.4) return "red";
  if (v < 3.6) return "amber";
  return "green";
}

export function DeviceHealthList({ devices }: { devices: Device[] }) {
  if (devices.length === 0) {
    return <p className="text-sm text-slate-400">No devices registered.</p>;
  }

  return (
    <ul className="divide-y divide-slate-100">
      {devices.map((d) => (
        <li key={d.id} className="flex items-center justify-between gap-3 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-800">{d.name}</p>
            <p className="truncate font-mono text-xs text-slate-400">{d.device_uid}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2 text-xs text-slate-500">
            <StatusPill label={metricValue(d.last_battery_v, "V", 2)} tone={batteryTone(d.last_battery_v)} />
            <span className="hidden sm:inline">
              {d.last_rssi !== null ? `${d.last_rssi} dBm` : "—"}
            </span>
            <span className="w-16 text-right">{relativeTime(d.last_seen_at)}</span>
            <StatusPill label={d.status} tone={statusTone(d.status)} />
          </div>
        </li>
      ))}
    </ul>
  );
}
