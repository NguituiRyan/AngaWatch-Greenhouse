/** Live latest-reading tiles for a greenhouse (auto-refreshes every 30s). */

import { useLatestReading } from "@/hooks/useReadings";
import type { Reading } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { metricValue, relativeTime } from "@/lib/format";

interface Tile {
  label: string;
  key: keyof Reading;
  unit: string;
  digits?: number;
}

const TILES: Tile[] = [
  { label: "Air temp", key: "air_temp_c", unit: "°C" },
  { label: "Humidity", key: "rh_pct", unit: "%", digits: 0 },
  { label: "Soil moisture", key: "soil_moisture_pct", unit: "%", digits: 0 },
  { label: "Soil temp", key: "soil_temp_c", unit: "°C" },
  { label: "Leaf wetness", key: "leaf_wetness", unit: "" },
  { label: "PPFD", key: "ppfd", unit: "µmol", digits: 0 },
  { label: "Pheromone trap", key: "pheromone_count", unit: "", digits: 0 },
  { label: "Water flow", key: "water_flow_l_per_min", unit: "L/min" },
];

export function LatestValues({ greenhouseId }: { greenhouseId: string }) {
  const { data, isLoading, error } = useLatestReading(greenhouseId);

  return (
    <Card
      title="Live readings"
      action={
        data ? (
          <span className="text-xs text-slate-400">updated {relativeTime(data.time)}</span>
        ) : null
      }
    >
      {isLoading ? (
        <Spinner />
      ) : error ? (
        <ErrorState error={error} />
      ) : !data ? (
        <EmptyState title="No readings yet" hint="Waiting for the first telemetry from this greenhouse." />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {TILES.map((t) => (
            <div key={t.label} className="rounded-lg bg-slate-50 p-3">
              <p className="text-xs text-slate-400">{t.label}</p>
              <p className="mt-0.5 text-lg font-semibold text-slate-900">
                {metricValue(data[t.key] as number | null, t.unit, t.digits ?? 1)}
              </p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
