/** Org-wide device inventory + health + the MQTT connection info to wire an ESP node. */

import { useDevices } from "@/hooks/useDevices";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { humanize, metricValue, relativeTime } from "@/lib/format";
import { isOnline, nodeTopics } from "@/lib/live";
import type { Device } from "@/lib/types";

function NodeConnectionCard({ nodes }: { nodes: Device[] }) {
  if (nodes.length === 0) return null;
  const first = nodes[0];
  return (
    <Card className="mt-6">
      <h3 className="text-sm font-semibold text-slate-800">Connect a node (MQTT)</h3>
      <p className="mt-1 text-xs text-slate-500">
        Flash <span className="font-mono">firmware/</span> (env{" "}
        <span className="font-mono">esp32-wifi</span>) with these in{" "}
        <span className="font-mono">secrets.h</span>, or emulate one with no hardware:{" "}
        <span className="font-mono">
          python scripts/esp_emulator.py --org-id {first.org_id} --uid {first.device_uid}
        </span>
      </p>
      <div className="mt-3 space-y-3">
        {nodes.map((d) => {
          const t = nodeTopics(d.org_id, d.device_uid);
          return (
            <div key={d.id} className="rounded-lg border border-slate-200 p-3">
              <p className="font-mono text-xs font-medium text-slate-700">{d.device_uid}</p>
              <dl className="mt-2 grid grid-cols-1 gap-1 font-mono text-[11px] text-slate-500 sm:grid-cols-3">
                <div>
                  <dt className="text-slate-400">telemetry →</dt>
                  <dd className="break-all text-emerald-700">{t.telemetry}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">command ←</dt>
                  <dd className="break-all text-sky-700">{t.command}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">state →</dt>
                  <dd className="break-all text-emerald-700">{t.state}</dd>
                </div>
              </dl>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

export function DevicesPage() {
  const { data, isLoading, error } = useDevices();

  const devices = data ?? [];
  const online = devices.filter((d) => isOnline(d.last_seen_at)).length;
  const nodes = devices.filter((d) => d.device_type === "sensor_node");

  return (
    <div>
      <PageHeader
        title="Devices"
        subtitle="Sensor nodes, gateways and actuators across your farms"
        actions={
          data ? <StatusPill label={`${online}/${devices.length} online`} tone="green" /> : undefined
        }
      />

      <Card>
        {isLoading ? (
          <Spinner />
        ) : error ? (
          <ErrorState error={error} />
        ) : devices.length === 0 ? (
          <EmptyState title="No devices registered" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-4 font-medium">Device</th>
                  <th className="py-2 pr-4 font-medium">Type</th>
                  <th className="py-2 pr-4 font-medium">Battery</th>
                  <th className="py-2 pr-4 font-medium">RSSI</th>
                  <th className="py-2 pr-4 font-medium">Last seen</th>
                  <th className="py-2 pr-4 font-medium">Link</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {devices.map((d) => {
                  const live = isOnline(d.last_seen_at);
                  return (
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
                          label={live ? "online" : "offline"}
                          tone={live ? "green" : "slate"}
                        />
                      </td>
                      <td className="py-3 pr-4">
                        <StatusPill
                          label={d.status}
                          tone={
                            d.status === "active" ? "green" : d.status === "fault" ? "red" : "slate"
                          }
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <NodeConnectionCard nodes={nodes} />
    </div>
  );
}
