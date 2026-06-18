/**
 * Current risk per model for a greenhouse, each with its plain-language
 * recommendation (matched by `risk_assessment_id`, falling back to the most
 * recent recommendation for the same alert/model).
 */

import { useRisk } from "@/hooks/useRisk";
import { useRecommendations } from "@/hooks/useRecommendations";
import type { Recommendation, RiskAssessment } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { RiskBadge } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { formatDateTime, humanize } from "@/lib/format";

function recommendationFor(
  assessment: RiskAssessment,
  recommendations: Recommendation[],
): Recommendation | undefined {
  return recommendations.find((r) => r.risk_assessment_id === assessment.id);
}

function recommendationText(rec: Recommendation): string {
  return rec.overridden && rec.override_message ? rec.override_message : rec.message_en;
}

export function RiskPanel({ greenhouseId }: { greenhouseId: string }) {
  const risk = useRisk(greenhouseId);
  const recs = useRecommendations(200);

  return (
    <Card title="Risk &amp; recommendations">
      {risk.isLoading ? (
        <Spinner />
      ) : risk.error ? (
        <ErrorState error={risk.error} />
      ) : (risk.data ?? []).length === 0 ? (
        <EmptyState title="No risk assessments yet" hint="The risk engine has not run for this greenhouse." />
      ) : (
        <ul className="space-y-3">
          {risk
            .data!.slice()
            .sort((a, b) => b.score - a.score)
            .map((a) => {
              const rec = recommendationFor(a, recs.data ?? []);
              return (
                <li key={a.id} className="rounded-lg border border-slate-100 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-800">
                      {humanize(a.model_type)}
                    </p>
                    <RiskBadge level={a.level} />
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    Score {a.score.toFixed(0)} · {formatDateTime(a.evaluated_at)}
                  </p>
                  {rec ? (
                    <p className="mt-2 text-sm text-slate-600">
                      {recommendationText(rec)}
                      {rec.overridden ? (
                        <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
                          agronomist override
                        </span>
                      ) : null}
                    </p>
                  ) : a.level === "none" || a.level === "low" ? (
                    <p className="mt-2 text-sm text-slate-400">No action needed.</p>
                  ) : null}
                </li>
              );
            })}
        </ul>
      )}
    </Card>
  );
}
