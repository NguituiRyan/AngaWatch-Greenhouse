/** Org-wide device inventory + health (battery, last-seen, RSSI, status). */

import { useDevices } from "@/hooks/useDevices";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { humanize, metricValue, relativeTime } from "@/lib/format";

export function DevicesPage() {
  const { data, isLoading, error } = useDevices();

  const online = (data ?? []).filter((d) => d.status === "active").length;

  return (
    <div>
      <PageHeader
        title="Devices"
        subtitle="Sensor nodes, gateways and actuators across your farms"
        actions={
          data ? <StatusPill label={`${online}/${data.length} online`} tone="green" /> : undefined
        }
      />

      <Card>
        {isLoading ? (
          <Spinner />
        ) : error ? (
          <ErrorState error={error} />
        ) : (data ?? []).length === 0 ? (
          <EmptyState title="No devices registered" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-4 font-medium">Device</th>
                  <th className="py-2 pr-4 font-medium">Type</th>
                  <th className="py-2 pr-4 font-medium">Battery</th>
                  <th className="py-2 pr-4 font-medium">RSSI</th>
                  <th className="py-2 pr-4 font-medium">Last seen</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data!.map((d) => (
                  <tr key={d.id}>
                    <td className="py-3 pr-4">
                      <p className="font-medium text-slate-800">{d.name}</p>
                      <p className="font-mono text-xs text-slate-400">{d.device_uid}</p>
                    </td>
                    <td className="py-3 pr-4 text-slate-600">{humanize(d.device_type)}</td>
                    <td className="py-3 pr-4 text-slate-600">
                      {metricValue(d.last_battery_v, "V", 2)}
                    </td>
                    <td className="py-3 pr-4 text-slate-600">
                      {d.last_rssi !== null ? `${d.last_rssi} dBm` : "—"}
                    </td>
                    <td className="py-3 pr-4 text-slate-600">{relativeTime(d.last_seen_at)}</td>
                    <td className="py-3 pr-4">
                      <StatusPill
                        label={d.status}
                        tone={d.status === "active" ? "green" : d.status === "fault" ? "red" : "slate"}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
