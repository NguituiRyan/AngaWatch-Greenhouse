/** Org alert feed with a status filter and inline acknowledge. */

import { useState } from "react";

import { useAlerts, useAckAlert } from "@/hooks/useAlerts";
import type { AlertStatus } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { AlertRow } from "@/components/AlertRow";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { humanize } from "@/lib/format";

const FILTERS: (AlertStatus | "all")[] = ["all", "pending", "sent", "escalated", "acked"];

export function AlertsPage() {
  const [filter, setFilter] = useState<AlertStatus | "all">("all");
  const { data, isLoading, error } = useAlerts(filter === "all" ? undefined : filter, 200);
  const ack = useAckAlert();

  return (
    <div>
      <PageHeader title="Alerts" subtitle="Risk alerts across your cooperative" />

      <Card>
        <div className="mb-3 flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                filter === f
                  ? "bg-brand text-brand-fg"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {f === "all" ? "All" : humanize(f)}
            </button>
          ))}
        </div>

        {isLoading ? (
          <Spinner />
        ) : error ? (
          <ErrorState error={error} />
        ) : (data ?? []).length === 0 ? (
          <EmptyState title="No alerts in this view" />
        ) : (
          <div className="divide-y divide-slate-100">
            {data!.map((a) => (
              <AlertRow
                key={a.id}
                alert={a}
                onAck={(id) => ack.mutate(id)}
                acking={ack.isPending && ack.variables === a.id}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
