/**
 * Recommendations feed.
 *
 * Lists plain-language actions (EN + SW). Agronomists / coop admins can override
 * a recommendation's message via an inline form (POST /recommendations/{id}/override).
 */

import { useState } from "react";

import { useRecommendations, useOverrideRecommendation } from "@/hooks/useRecommendations";
import { useAuth } from "@/context/AuthContext";
import type { Recommendation } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { formatDateTime, humanize } from "@/lib/format";

function OverrideForm({
  recommendation,
  onClose,
}: {
  recommendation: Recommendation;
  onClose: () => void;
}) {
  const override = useOverrideRecommendation();
  const [message, setMessage] = useState(recommendation.override_message ?? "");

  async function submit() {
    if (!message.trim()) return;
    await override.mutateAsync({ recommendationId: recommendation.id, message: message.trim() });
    onClose();
  }

  return (
    <div className="mt-3 rounded-lg bg-slate-50 p-3">
      <label className="label" htmlFor={`override-${recommendation.id}`}>
        Agronomist override
      </label>
      <textarea
        id={`override-${recommendation.id}`}
        className="input min-h-[72px]"
        value={message}
        maxLength={2000}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Replace the automated advice with your guidance…"
      />
      {override.isError ? (
        <p className="mt-1 text-xs text-red-600">{(override.error as Error).message}</p>
      ) : null}
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          className="btn-primary px-3 py-1.5 text-xs"
          onClick={submit}
          disabled={override.isPending || !message.trim()}
        >
          {override.isPending ? "Saving…" : "Save override"}
        </button>
        <button type="button" className="btn-secondary px-3 py-1.5 text-xs" onClick={onClose}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function RecommendationCard({
  recommendation,
  canOverride,
}: {
  recommendation: Recommendation;
  canOverride: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const text =
    recommendation.overridden && recommendation.override_message
      ? recommendation.override_message
      : recommendation.message_en;

  return (
    <div className="rounded-lg border border-slate-100 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-slate-800">
            {humanize(recommendation.action_code)}
          </p>
          <p className="text-xs text-slate-400">Priority {recommendation.priority}</p>
        </div>
        {recommendation.overridden ? <StatusPill label="Overridden" tone="amber" /> : null}
      </div>

      <p className="mt-2 text-sm text-slate-700">{text}</p>
      <p className="mt-1 text-xs italic text-slate-400">{recommendation.message_sw}</p>

      {recommendation.overridden && recommendation.override_at ? (
        <p className="mt-1 text-xs text-slate-400">
          Overridden {formatDateTime(recommendation.override_at)}
        </p>
      ) : null}

      {canOverride ? (
        editing ? (
          <OverrideForm recommendation={recommendation} onClose={() => setEditing(false)} />
        ) : (
          <button
            type="button"
            className="btn-secondary mt-3 px-3 py-1.5 text-xs"
            onClick={() => setEditing(true)}
          >
            {recommendation.overridden ? "Edit override" : "Override"}
          </button>
        )
      ) : null}
    </div>
  );
}

export function RecommendationsPage() {
  const { user } = useAuth();
  const { data, isLoading, error } = useRecommendations(200);
  const canOverride = user?.role === "agronomist" || user?.role === "coop_admin";

  return (
    <div>
      <PageHeader
        title="Recommendations"
        subtitle="Plain-language actions, with agronomist overrides"
      />

      <Card>
        {isLoading ? (
          <Spinner />
        ) : error ? (
          <ErrorState error={error} />
        ) : (data ?? []).length === 0 ? (
          <EmptyState title="No recommendations yet" />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {data!.map((r) => (
              <RecommendationCard key={r.id} recommendation={r} canOverride={canOverride} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
