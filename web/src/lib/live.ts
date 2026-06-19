/**
 * Live-data helpers for the hardware-connected dashboard.
 *
 * `LIVE_REFETCH_MS` drives TanStack Query polling so the UI tracks a real ESP
 * node in near real time. It is disabled in demo mode (the fixtures are static,
 * and polling them is pointless).
 */

import { DEMO_MODE } from "@/lib/demo";

/** Poll interval (ms) for live queries; `false` (no polling) in demo mode. */
export const LIVE_REFETCH_MS: number | false = DEMO_MODE ? false : 10_000;

/** A node counts as "online" if it reported within `thresholdMs` (default 5 min). */
export function isOnline(lastSeenAt: string | null, thresholdMs = 5 * 60_000): boolean {
  if (!lastSeenAt) return false;
  const t = Date.parse(lastSeenAt);
  if (Number.isNaN(t)) return false;
  return Date.now() - t < thresholdMs;
}

/** The MQTT topics a node uses — shown so you can flash matching firmware. */
export function nodeTopics(orgId: string, deviceUid: string) {
  const base = `farm/${orgId}/${deviceUid}`;
  return {
    telemetry: `${base}/telemetry`,
    command: `${base}/command`,
    state: `${base}/state`,
  };
}
