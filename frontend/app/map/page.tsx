"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import AqiLegend from "@/components/AqiLegend";
import {
  getForecast,
  getGridCells,
  getGridReadings,
  getRecommendations,
  type AgentRun,
  type ForecastResponse,
  type GridCellInfo,
  type GridReadingsResponse,
} from "@/lib/api";
import { PageHeader, Skeleton } from "@/components/ui";

const AqiMap = dynamic(() => import("@/components/AqiMap"), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full" />,
});

const HORIZON_STEPS = [
  { label: "Live", step: null },
  { label: "+1h", step: 1 },
  { label: "+6h", step: 6 },
  { label: "+12h", step: 12 },
  { label: "+24h", step: 24 },
  { label: "+48h", step: 48 },
  { label: "+72h", step: 72 },
] as const;

export default function MapPage() {
  const [cells, setCells] = useState<GridCellInfo[]>([]);
  const [readings, setReadings] = useState<GridReadingsResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [agentRun, setAgentRun] = useState<AgentRun | null>(null);
  const [forecastStep, setForecastStep] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    getGridCells().then((d) => setCells(d.cells)).catch(() => {});
    getGridReadings().then(setReadings).catch(() => {});
    getForecast("delhi-ncr", 72).then(setForecast).catch(() => {});
    getRecommendations()
      .then((d) => d.runs.length > 0 && setAgentRun(d.runs[0]))
      .catch(() => {});
  }, []);

  return (
    <>
      <PageHeader
        title="Live AQI Map"
        subtitle="1 km IDW-interpolated PM2.5 surface. Scrub the timeline to preview the ConvLSTM forecast; enforcement routes from the latest agent run are overlaid."
      />

      <div
        className="flex flex-wrap items-center gap-2"
        role="radiogroup"
        aria-label="Forecast horizon"
      >
        {HORIZON_STEPS.map(({ label, step }) => {
          const disabled = step !== null && (!forecast || !forecast.horizons[String(step)]);
          const active = forecastStep === step;
          return (
            <button
              key={label}
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => setForecastStep(step)}
              className={`ux4g-btn ux4g-btn-xs rounded-lg px-3 text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-gov-400 ${
                active
                  ? "ux4g-btn-primary"
                  : disabled
                    ? "ux4g-btn-outline-neutral cursor-not-allowed opacity-50"
                    : "ux4g-btn-outline-neutral"
              }`}
            >
              {label}
            </button>
          );
        })}
        {readings?.measured_at && (
          <span className="ml-2 text-xs text-neutral-500">
            snapshot {new Date(readings.measured_at).toLocaleString()}
          </span>
        )}
        <span aria-live="polite" className="ml-auto text-xs text-gov-700">
          {selected}
        </span>
      </div>

      <div className="mt-3 h-[calc(100vh-310px)] min-h-[420px]">
        <AqiMap
          cells={cells}
          readings={readings}
          forecast={forecast}
          forecastStep={forecastStep}
          agentRun={agentRun}
          onCellClick={(cell, v) =>
            setSelected(`cell ${cell.grid_id} · PM2.5 ${v?.toFixed(0) ?? "—"} µg/m³`)
          }
        />
      </div>

      <div className="mt-3">
        <AqiLegend />
      </div>
    </>
  );
}
