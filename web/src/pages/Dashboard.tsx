/**
 * Org overview dashboard.
 *
 * Top-line stats, every greenhouse with its current risk badge, the recent
 * alert feed, and org-wide device health.
 */

import { PageHeader } from "@/components/PageHeader";
import { Card, StatTile } from "@/components/ui/Card";
import { GreenhouseCard } from "@/components/GreenhouseCard";
import { DeviceHealthList } from "@/components/DeviceHealthList";
import { AlertRow } from "@/components/AlertRow";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { useGreenhouses } from "@/hooks/useGreenhouses";
import { useDevices } from "@/hooks/useDevices";
import { useAlerts, useAckAlert } from "@/hooks/useAlerts";

export function DashboardPage() {
  const greenhouses = useGreenhouses();
  const devices = useDevices();
  const alerts = useAlerts(undefined, 8);
  const ack = useAckAlert();

  const openAlerts = (alerts.data ?? []).filter((a) => a.status !== "acked").length;
  const onlineDevices = (devices.data ?? []).filter((d) => d.status === "active").length;

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Live overview of your greenhouses and devices" />

      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <StatTile label="Greenhouses" value={greenhouses.data?.length ?? "—"} />
        <StatTile
          label="Devices online"
          value={`${onlineDevices}/${devices.data?.length ?? 0}`}
        />
        <StatTile label="Open alerts" value={openAlerts} />
        <StatTile label="Total alerts" value={alerts.data?.length ?? "—"} hint="recent feed" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Greenhouses with current risk */}
        <div className="lg:col-span-2">
          <Card title="Greenhouses">
            {greenhouses.isLoading ? (
              <Spinner />
            ) : greenhouses.error ? (
              <ErrorState error={greenhouses.error} />
            ) : (greenhouses.data ?? []).length === 0 ? (
              <EmptyState title="No greenhouses yet" hint="Add a greenhouse to start monitoring." />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {greenhouses.data!.map((gh) => (
                  <GreenhouseCard key={gh.id} greenhouse={gh} />
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Recent alerts */}
        <div className="space-y-6">
          <Card title="Recent alerts">
            {alerts.isLoading ? (
              <Spinner />
            ) : alerts.error ? (
              <ErrorState error={alerts.error} />
            ) : (alerts.data ?? []).length === 0 ? (
              <EmptyState title="No alerts" />
            ) : (
              <div className="divide-y divide-slate-100">
                {alerts.data!.map((a) => (
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
      </div>

      <div className="mt-6">
        <Card title="Device health">
          {devices.isLoading ? (
            <Spinner />
          ) : devices.error ? (
            <ErrorState error={devices.error} />
          ) : (
            <DeviceHealthList devices={devices.data ?? []} />
          )}
        </Card>
      </div>
    </div>
  );
}
