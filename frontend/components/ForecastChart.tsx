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

// Palette validated for the white surface (#ffffff) with scripts/validate_palette.js:
// lightness band, chroma, CVD ΔE and 3:1 contrast all pass. Persistence is also
// dashed so identity never rests on color alone.
const FORECAST_COLOR = "#4a2bc2";
const PERSISTENCE_COLOR = "#c47d00";

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
            <CartesianGrid stroke="#e5e5e5" strokeDasharray="3 6" vertical={false} />
            <XAxis
              dataKey="step"
              tickFormatter={(v: number) => (v === 0 ? "now" : `+${v}h`)}
              tick={{ fill: "#525252", fontSize: 11 }}
              axisLine={{ stroke: "#d9d9d9" }}
              tickLine={false}
            />
            <YAxis
              width={44}
              tick={{ fill: "#525252", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              label={{
                value: "µg/m³",
                angle: -90,
                position: "insideLeft",
                fill: "#737373",
                fontSize: 11,
              }}
            />
            <Tooltip
              cursor={{ stroke: "#a1a1a1", strokeDasharray: "4 4" }}
              contentStyle={{
                background: "#ffffff",
                border: "1px solid #d9d9d9",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "#404040" }}
              labelFormatter={(v) => (Number(v) === 0 ? "Now" : `+${v} hours`)}
              formatter={(value, name) => [`${Number(value).toFixed(1)} µg/m³`, name]}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, color: "#525252" }}
              iconType="plainline"
            />
            <Line
              name="ConvLSTM forecast (city mean)"
              type="monotone"
              dataKey="forecast"
              stroke={FORECAST_COLOR}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 2, stroke: "#ffffff" }}
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
              activeDot={{ r: 5, strokeWidth: 2, stroke: "#ffffff" }}
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
