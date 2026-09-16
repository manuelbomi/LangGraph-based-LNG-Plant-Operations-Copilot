import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ReadingPoint } from "../api/types";

interface SensorChartProps {
  readings: ReadingPoint[];
  unit: string;
  normalMin: number;
  normalMax: number;
  criticalMin: number;
  criticalMax: number;
  /** The specific reading to highlight as the anomaly point, if any. */
  highlight?: { timestamp: string; value: number; classification: "normal" | "warning" | "critical" | string };
}

const HIGHLIGHT_COLOR: Record<string, string> = {
  normal: "#0d9488", // teal-600
  warning: "#d97706", // amber-600
  critical: "#e11d48", // rose-600
};

function formatTick(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, "0")}:00`;
}

interface TooltipPayloadItem {
  value: number;
  payload: { timestamp: string };
}

function ChartTooltip({ active, payload, unit }: { active?: boolean; payload?: TooltipPayloadItem[]; unit: string }) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0];
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs shadow-sm">
      <div className="font-medium text-slate-700">{new Date(point.payload.timestamp).toUTCString()}</div>
      <div className="text-slate-500">
        {point.value.toFixed(2)} {unit}
      </div>
    </div>
  );
}

/** A time-series chart of a sensor tag's recent readings, with its normal
 * operating band shown as a shaded reference area, critical thresholds as
 * dashed reference lines, and (when provided) the specific anomaly point
 * highlighted with a colored dot matching its severity. One series, one
 * axis -- no dual-axis, no rainbow. */
export function SensorChart({ readings, unit, normalMin, normalMax, criticalMin, criticalMax, highlight }: SensorChartProps) {
  if (readings.length === 0) {
    return <p className="text-sm text-slate-400">No readings available for this window.</p>;
  }

  const values = readings.map((r) => r.value);
  const yMin = Math.min(criticalMin, ...values);
  const yMax = Math.max(criticalMax, ...values);
  const pad = (yMax - yMin) * 0.08 || 1;

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={readings} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
        <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatTick}
          tick={{ fontSize: 10, fill: "#94a3b8" }}
          minTickGap={40}
          axisLine={{ stroke: "#cbd5e1" }}
          tickLine={false}
        />
        <YAxis
          domain={[yMin - pad, yMax + pad]}
          tick={{ fontSize: 10, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
          width={56}
          label={{ value: unit, angle: -90, position: "insideLeft", fontSize: 10, fill: "#94a3b8" }}
        />
        <Tooltip content={<ChartTooltip unit={unit} />} />

        <ReferenceArea y1={normalMin} y2={normalMax} fill="#10b981" fillOpacity={0.08} strokeOpacity={0} />
        <ReferenceLine y={criticalMax} stroke="#e11d48" strokeDasharray="4 4" strokeOpacity={0.6} />
        <ReferenceLine y={criticalMin} stroke="#e11d48" strokeDasharray="4 4" strokeOpacity={0.6} />

        <Line
          type="monotone"
          dataKey="value"
          stroke="#265d9c"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />

        {highlight && (
          <ReferenceDot
            x={highlight.timestamp}
            y={highlight.value}
            r={7}
            fill={HIGHLIGHT_COLOR[highlight.classification] ?? "#e11d48"}
            stroke="#ffffff"
            strokeWidth={2}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
