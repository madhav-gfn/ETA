"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import AdvisoryCard from "@/components/AdvisoryCard";
import EnforcementPanel from "@/components/EnforcementPanel";
import {
  getForecast,
  getForecastMetrics,
  getGridCells,
  getGridReadings,
  getRecommendations,
  runAgentDrill,
  type AgentRun,
  type ForecastMetrics,
  type ForecastResponse,
  type GridCellInfo,
  type GridReadingsResponse,
} from "@/lib/api";

const AqiMap = dynamic(() => import("@/components/AqiMap"), { ssr: false });

const HORIZON_STEPS = [
  { label: "Live", step: null },
  { label: "+1h", step: 1 },
  { label: "+6h", step: 6 },
  { label: "+12h", step: 12 },
  { label: "+24h", step: 24 },
  { label: "+48h", step: 48 },
  { label: "+72h", step: 72 },
] as const;

export default function Dashboard() {
  const [cells, setCells] = useState<GridCellInfo[]>([]);
  const [readings, setReadings] = useState<GridReadingsResponse | null>(null);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [metrics, setMetrics] = useState<ForecastMetrics | null>(null);
  const [forecastStep, setForecastStep] = useState<number | null>(null);
  const [agentRun, setAgentRun] = useState<AgentRun | null>(null);
  const [drillRunning, setDrillRunning] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    getGridCells().then((d) => setCells(d.cells)).catch(() => {});
    getGridReadings().then(setReadings).catch(() => {});
    getForecast("delhi-ncr", 72).then(setForecast).catch(() => setForecast(null));
    getForecastMetrics().then(setMetrics).catch(() => setMetrics(null));
    getRecommendations()
      .then((d) => d.runs.length > 0 && setAgentRun(d.runs[0]))
      .catch(() => {});
  }, []);

  const onDrill = useCallback(() => {
    setDrillRunning(true);
    // Central-Delhi cell for a realistic drill site.
    const central = cells.find((c) => c.row_idx === 27 && c.col_idx === 23);
    runAgentDrill("delhi-ncr", central?.grid_id)
      .then((d) => {
        if (d.anomaly_found) setAgentRun(d);
      })
      .finally(() => setDrillRunning(false));
  }, [cells]);

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            UrbanAir Intel <span className="text-sky-400">· Delhi NCR</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            1km digital twin — live AQI, 72h hyperlocal forecast, source attribution &amp;
            enforcement dispatch.
          </p>
        </div>
        {metrics?.model_available && (
          <div className="rounded-md border border-slate-800 bg-slate-900/60 px-3 py-2 text-xs text-slate-300">
            {metrics.model_rmse_24h !== undefined ? (
              <>
                24h RMSE {metrics.model_rmse_24h} vs persistence {metrics.persistence_rmse_24h}{" "}
                {metrics.beats_persistence_24h ? (
                  <span className="text-emerald-400">✓ beats baseline</span>
                ) : (
                  <span className="text-amber-400">(baseline ahead)</span>
                )}
              </>
            ) : (
              <>
                1h RMSE {metrics.model_rmse_1h} vs persistence {metrics.persistence_rmse_1h}{" "}
                {metrics.beats_persistence ? (
                  <span className="text-emerald-400">✓ beats baseline</span>
                ) : (
                  <span className="text-amber-400">(baseline ahead)</span>
                )}
              </>
            )}
          </div>
        )}
      </header>

      <div className="flex flex-wrap items-center gap-2">
        {HORIZON_STEPS.map(({ label, step }) => {
          const disabled = step !== null && (!forecast || !forecast.horizons[String(step)]);
          return (
            <button
              key={label}
              disabled={disabled}
              onClick={() => setForecastStep(step)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                forecastStep === step
                  ? "bg-sky-600 text-white"
                  : disabled
                    ? "cursor-not-allowed bg-slate-900 text-slate-600"
                    : "bg-slate-800 text-slate-300 hover:bg-slate-700"
              }`}
            >
              {label}
            </button>
          );
        })}
        {readings?.measured_at && (
          <span className="ml-2 text-xs text-slate-500">
            live snapshot: {new Date(readings.measured_at).toLocaleString()}
          </span>
        )}
        {selected && <span className="ml-auto text-xs text-sky-300">{selected}</span>}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="h-[540px] lg:col-span-2">
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
        <div className="flex flex-col gap-4">
          <AdvisoryCard />
          <EnforcementPanel run={agentRun} onDrill={onDrill} drillRunning={drillRunning} />
        </div>
      </div>
    </main>
  );
}
