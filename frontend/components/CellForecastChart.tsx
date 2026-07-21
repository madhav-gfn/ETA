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

// Same CVD-validated palette as ForecastChart.tsx, roles swapped: observed is
// the primary (solid) series here, forecast is secondary (dashed).
const OBSERVED_COLOR = "#4a2bc2";
const FORECAST_COLOR = "#c47d00";

export interface CellChartPoint {
  timestamp: string; // ISO
  observed: number | null;
  forecast: number | null;
}

export default function CellForecastChart({ data }: { data: CellChartPoint[] }) {
  return (
    <figure aria-label="Observed and forecast PM2.5 for the selected grid cell">
      <div className="h-72 w-full">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#e5e5e5" strokeDasharray="3 6" vertical={false} />
            <XAxis
              dataKey="timestamp"
              tickFormatter={(v: string) => new Date(v).toLocaleTimeString([], { hour: "2-digit" })}
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
              labelFormatter={(v) => new Date(v as string).toLocaleString()}
              formatter={(value, name) => [`${Number(value).toFixed(1)} µg/m³`, name]}
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#525252" }} iconType="plainline" />
            <Line
              name="Observed"
              type="monotone"
              dataKey="observed"
              stroke={OBSERVED_COLOR}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 2, stroke: "#ffffff" }}
              connectNulls
            />
            <Line
              name="Forecast"
              type="monotone"
              dataKey="forecast"
              stroke={FORECAST_COLOR}
              strokeWidth={2}
              strokeDasharray="6 5"
              dot={false}
              activeDot={{ r: 5, strokeWidth: 2, stroke: "#ffffff" }}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 text-xs text-neutral-500">
        Solid line is observed PM2.5 at this cell; dashed line is the ConvLSTM rollout
        continuing from the last observed hour.
      </figcaption>
    </figure>
  );
}
