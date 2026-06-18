/** Risk-level badge + a generic status pill. */

import type { RiskLevel } from "@/lib/types";
import { RISK_BADGE, humanize } from "@/lib/format";

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${RISK_BADGE[level]}`}
    >
      {humanize(level)}
    </span>
  );
}

export function StatusPill({ label, tone = "slate" }: { label: string; tone?: string }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700",
    green: "bg-green-100 text-green-800",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-red-100 text-red-800",
    blue: "bg-blue-100 text-blue-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
        tones[tone] ?? tones.slate
      }`}
    >
      {label}
    </span>
  );
}
