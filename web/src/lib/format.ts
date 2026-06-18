/** Small presentation helpers shared across pages. */

import type { RiskLevel } from "./types";

/** Tailwind classes (badge bg + text) per risk level. */
export const RISK_BADGE: Record<RiskLevel, string> = {
  none: "bg-green-100 text-green-800",
  low: "bg-lime-100 text-lime-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};

export const RISK_RANK: Record<RiskLevel, number> = {
  none: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
};

/** Human label for a snake_case enum / model type. */
export function humanize(value: string): string {
  return value
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/** Format an ISO timestamp as a short local date-time, or a dash when null. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Relative "x ago" string for last-seen style fields. */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "never";
  const diffMs = Date.now() - then;
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

/** Format a numeric reading value with a unit, or a dash when null. */
export function metricValue(value: number | null | undefined, unit = "", digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

/** Highest risk level among a list of assessments (for org-overview badges). */
export function highestRisk(levels: RiskLevel[]): RiskLevel {
  return levels.reduce<RiskLevel>(
    (acc, lvl) => (RISK_RANK[lvl] > RISK_RANK[acc] ? lvl : acc),
    "none",
  );
}
