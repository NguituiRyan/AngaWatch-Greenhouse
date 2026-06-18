/**
 * Greenhouse detail.
 *
 * Live latest values, historical line charts (temp / RH / soil moisture),
 * current risk per model with recommendations, manual actuator control, and
 * device health for the greenhouse's nodes.
 */

import { Link, useParams } from "react-router-dom";

import { useGreenhouse } from "@/hooks/useGreenhouses";
import { useReadings } from "@/hooks/useReadings";
import { useDevices } from "@/hooks/useDevices";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { LatestValues } from "@/components/LatestValues";
import { ReadingsChart } from "@/components/ReadingsChart";
import { RiskPanel } from "@/components/RiskPanel";
import { ActuatorControls } from "@/components/ActuatorControls";
import { DeviceHealthList } from "@/components/DeviceHealthList";
import { ErrorState, Spinner } from "@/components/ui/States";

export function GreenhouseDetailPage() {
  const { greenhouseId } = useParams<{ greenhouseId: string }>();
  const greenhouse = useGreenhouse(greenhouseId);
  const readings = useReadings(greenhouseId, { limit: 500 });
  const devices = useDevices(greenhouseId);

  if (greenhouse.isLoading) return <Spinner label="Loading greenhouse…" />;
  if (greenhouse.error) return <ErrorState error={greenhouse.error} />;
  if (!greenhouse.data) return <ErrorState error={new Error("Greenhouse not found")} />;

  const rows = readings.data ?? [];

  return (
    <div>
      <PageHeader
        title={greenhouse.data.name}
        subtitle={
          <span>
            {greenhouse.data.zone ? `${greenhouse.data.zone} · ` : ""}
            {greenhouse.data.structure_type ?? "Greenhouse"}
          </span>
        }
        actions={
          <Link to="/" className="btn-secondary px-3 py-1.5 text-xs">
            ← Dashboard
          </Link>
        }
      />

      <div className="space-y-6">
        <LatestValues greenhouseId={greenhouse.data.id} />

        {/* Historical charts */}
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="Air temperature (°C)">
            {readings.isLoading ? (
              <Spinner />
            ) : (
              <ReadingsChart readings={rows} metric="air_temp_c" color="#ea580c" unit="°C" />
            )}
          </Card>
          <Card title="Relative humidity (%)">
            {readings.isLoading ? (
              <Spinner />
            ) : (
              <ReadingsChart readings={rows} metric="rh_pct" color="#2563eb" unit="%" />
            )}
          </Card>
          <Card title="Soil moisture (%)">
            {readings.isLoading ? (
              <Spinner />
            ) : (
              <ReadingsChart readings={rows} metric="soil_moisture_pct" color="#16a34a" unit="%" />
            )}
          </Card>
        </div>

        {/* Risk + control */}
        <div className="grid gap-6 lg:grid-cols-2">
          <RiskPanel greenhouseId={greenhouse.data.id} />
          <ActuatorControls greenhouseId={greenhouse.data.id} />
        </div>

        {/* Device health */}
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
