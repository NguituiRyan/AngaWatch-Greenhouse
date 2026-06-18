/**
 * Recharts line chart for a single telemetry metric over time.
 *
 * Readings come newest-first from the API; we reverse to ascending for the X
 * axis and format the timestamp to a short local time label.
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Reading, ReadingMetric } from "@/lib/types";

interface ReadingsChartProps {
  readings: Reading[];
  metric: ReadingMetric;
  color?: string;
  unit?: string;
}

export function ReadingsChart({ readings, metric, color = "#16a34a", unit }: ReadingsChartProps) {
  const data = [...readings]
    .reverse()
    .map((r) => ({
      t: new Date(r.time).toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
      }),
      value: r[metric] as number | null,
    }))
    .filter((d) => d.value !== null);

  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-slate-400">
        No data for this metric.
      </div>
    );
  }

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="t" tick={{ fontSize: 11, fill: "#94a3b8" }} minTickGap={28} />
          <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} width={44} />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
            formatter={(v: number) => [`${v}${unit ? ` ${unit}` : ""}`, ""]}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
