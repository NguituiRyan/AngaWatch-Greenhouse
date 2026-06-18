/** Dashboard tile: a greenhouse with its highest current risk + quick link. */

import { Link } from "react-router-dom";

import { useRisk } from "@/hooks/useRisk";
import type { Greenhouse } from "@/lib/types";
import { RiskBadge } from "@/components/ui/Badge";
import { highestRisk, humanize } from "@/lib/format";

export function GreenhouseCard({ greenhouse }: { greenhouse: Greenhouse }) {
  const { data: assessments, isLoading } = useRisk(greenhouse.id);

  const top = highestRisk((assessments ?? []).map((a) => a.level));
  const actionable = (assessments ?? []).filter(
    (a) => a.level === "medium" || a.level === "high" || a.level === "critical",
  );

  return (
    <Link
      to={`/greenhouses/${greenhouse.id}`}
      className="card block p-4 transition-shadow hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-slate-800">{greenhouse.name}</p>
          <p className="truncate text-xs text-slate-400">
            {greenhouse.zone ? `${greenhouse.zone} · ` : ""}
            {greenhouse.structure_type ?? "Greenhouse"}
          </p>
        </div>
        {isLoading ? (
          <span className="h-5 w-12 animate-pulse rounded-full bg-slate-100" />
        ) : (
          <RiskBadge level={top} />
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {actionable.length === 0 ? (
          <span className="text-xs text-slate-400">No active risks</span>
        ) : (
          actionable.map((a) => (
            <span
              key={a.id}
              className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600"
            >
              {humanize(a.model_type)}
            </span>
          ))
        )}
      </div>
    </Link>
  );
}
