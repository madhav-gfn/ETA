"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Palette validated for contrast with scripts/validate_palette.js: lightness
// band, chroma, CVD ΔE and 3:1 contrast all pass. Persistence is also dashed
// so identity never rests on color alone. Brightened for the dark surface.
const FORECAST_COLOR = "#8670ff";
const PERSISTENCE_COLOR = "#e89c30";
const CHART_SURFACE = "#0e0e15";

export interface ChartPoint {
  step: number; // hours ahead; 0 = now
  forecast: number | null;
  persistence: number;
}

export default function ForecastChart({ data }: { data: ChartPoint[] }) {
  return (
    <figure aria-label="City mean PM2.5 forecast versus persistence baseline">
      <div className="h-72 w-full">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#1c1c27" strokeDasharray="3 6" vertical={false} />
            <XAxis
              dataKey="step"
              tickFormatter={(v: number) => (v === 0 ? "now" : `+${v}h`)}
              tick={{ fill: "#8b8b9e", fontSize: 11 }}
              axisLine={{ stroke: "#2c2c3a" }}
              tickLine={false}
            />
            <YAxis
              width={44}
              tick={{ fill: "#8b8b9e", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              label={{
                value: "µg/m³",
                angle: -90,
                position: "insideLeft",
                fill: "#8b8b9e",
                fontSize: 11,
              }}
            />
            <Tooltip
              cursor={{ stroke: "#6c6c80", strokeDasharray: "4 4" }}
              contentStyle={{
                background: "#0e0e15",
                border: "1px solid #2c2c3a",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "#dddde6" }}
              itemStyle={{ color: "#c5c5d3" }}
              labelFormatter={(v) => (Number(v) === 0 ? "Now" : `+${v} hours`)}
              formatter={(value, name) => [`${Number(value).toFixed(1)} µg/m³`, name]}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, color: "#a9a9ba" }}
              iconType="plainline"
            />
            <Line
              name="ConvLSTM forecast (city mean)"
              type="monotone"
              dataKey="forecast"
              stroke={FORECAST_COLOR}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 2, stroke: CHART_SURFACE }}
              connectNulls
            />
            <Line
              name="Persistence baseline (today = tomorrow)"
              type="monotone"
              dataKey="persistence"
              stroke={PERSISTENCE_COLOR}
              strokeWidth={2}
              strokeDasharray="6 5"
              dot={false}
              activeDot={{ r: 5, strokeWidth: 2, stroke: CHART_SURFACE }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 text-xs text-neutral-500">
        The gap between the solid forecast line and the dashed persistence line is the
        model&apos;s value-add — the metric this platform is judged on. Full numbers in the
        table below.
      </figcaption>
    </figure>
  );
}
