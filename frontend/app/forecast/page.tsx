"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  getCellForecast,
  getForecast,
  getForecastMetrics,
  getGridReadings,
  type CellForecast,
  type ForecastMetrics,
  type ForecastResponse,
  type GridReadingsResponse,
} from "@/lib/api";
import Reveal from "@/components/fx/Reveal";

const ForecastChart = dynamic(() => import("@/components/ForecastChart"), { ssr: false });
const CellForecastChart = dynamic(() => import("@/components/CellForecastChart"), { ssr: false });
import type { CellChartPoint } from "@/components/CellForecastChart";
import { pm25Band } from "@/lib/aqi";
import {
  Badge,
  Card,
  CardTitle,
  EmptyState,
  PageHeader,
  PlannedNote,
  Skeleton,
  StatCard,
} from "@/components/ui";

export default function ForecastPage() {
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [metrics, setMetrics] = useState<ForecastMetrics | null>(null);
  const [readings, setReadings] = useState<GridReadingsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const [selectedGridId, setSelectedGridId] = useState<number | null>(null);
  const [cellForecast, setCellForecast] = useState<CellForecast | null>(null);
  const [cellLoading, setCellLoading] = useState(false);

  useEffect(() => {
    Promise.allSettled([
      getForecast("delhi-ncr", 72).then(setForecast),
      getForecastMetrics().then(setMetrics),
      getGridReadings().then(setReadings),
    ]).finally(() => setLoading(false));
  }, []);

  // Hottest currently-reporting cells — the natural drill-down candidates.
  const hotCells = useMemo(() => {
    if (!readings) return [];
    return [...readings.readings].sort((a, b) => b.value - a.value).slice(0, 5);
  }, [readings]);

  const loadCell = useCallback((gridId: number) => {
    setSelectedGridId(gridId);
    setCellLoading(true);
    getCellForecast(gridId, "delhi-ncr", 72)
      .then(setCellForecast)
      .catch(() => setCellForecast(null))
      .finally(() => setCellLoading(false));
  }, []);

  // Observed history (solid) bridged into the forecast rollout (dashed) at
  // the seam — the last observed point is duplicated onto the forecast series
  // so the two lines connect instead of leaving a visual gap.
  const cellChartData = useMemo(() => {
    if (!cellForecast) return [];
    const points: CellChartPoint[] = cellForecast.history.map((h, i, arr) => ({
      timestamp: h.timestep,
      observed: h.pm25,
      forecast: i === arr.length - 1 ? h.pm25 : null,
    }));
    cellForecast.forecast.forEach((f) => {
      points.push({ timestamp: f.timestep, observed: null, forecast: f.pm25 });
    });
    return points;
  }, [cellForecast]);

  // Per-horizon city mean / peak over valid cells.
  const rows = useMemo(() => {
    if (!forecast) return [];
    return Object.entries(forecast.horizons)
      .map(([step, frame]) => {
        const values: number[] = [];
        frame.pm25.forEach((row, r) =>
          row.forEach((v, c) => {
            if (forecast.valid_mask?.[r]?.[c]) values.push(v);
          })
        );
        if (values.length === 0) return null;
        const mean = values.reduce((a, b) => a + b, 0) / values.length;
        return {
          step: Number(step),
          timestep: frame.timestep,
          mean,
          max: Math.max(...values),
        };
      })
      .filter((r): r is NonNullable<typeof r> => r !== null)
      .sort((a, b) => a.step - b.step);
  }, [forecast]);

  // Chart series: model rollout vs flat persistence baseline anchored at the live mean.
  const chartData = useMemo(() => {
    if (rows.length === 0) return [];
    const liveMean =
      readings && readings.readings.length > 0
        ? readings.readings.reduce((a, r) => a + r.value, 0) / readings.readings.length
        : rows[0].mean;
    return [
      { step: 0, forecast: liveMean, persistence: liveMean },
      ...rows.map((r) => ({ step: r.step, forecast: r.mean, persistence: liveMean })),
    ];
  }, [rows, readings]);

  return (
    <>
      <PageHeader
        title="Hyperlocal Forecast"
        subtitle="ConvLSTM 24–72 h PM2.5 rollout at 1 km resolution, benchmarked against the persistence baseline the judging brief specifies."
      />

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard
            label="Model RMSE (24h direct)"
            value={metrics?.model_rmse_24h ?? "—"}
            unit="µg/m³"
            hint={metrics?.model_rmse_24h === undefined ? "24h-direct model not trained yet" : undefined}
          />
          <StatCard
            label="Persistence RMSE (24h)"
            value={metrics?.persistence_rmse_24h ?? metrics?.persistence_rmse_1h ?? "—"}
            unit="µg/m³"
            hint="baseline: tomorrow = today"
          />
          <StatCard
            label="Verdict"
            value={
              metrics ? (
                (metrics.beats_persistence_24h ?? metrics.beats_persistence) ? (
                  <span className="text-emerald-700">Beats baseline</span>
                ) : (
                  <span className="text-amber-700">Baseline ahead</span>
                )
              ) : (
                "—"
              )
            }
            hint={metrics ? `${metrics.test_windows} held-out test windows` : undefined}
          />
        </div>
      )}

      {chartData.length > 0 && (
        <Reveal delay={0.1} className="mt-6">
          <Card>
            <CardTitle>Forecast vs persistence — city mean PM2.5</CardTitle>
            <ForecastChart data={chartData} />
          </Card>
        </Reveal>
      )}

      <Card className="mt-6">
        <CardTitle
          actions={
            forecast && (
              <Badge tone="sky">generated from {new Date(forecast.generated_from).toLocaleString()}</Badge>
            )
          }
        >
          City-wide forecast by horizon
        </CardTitle>
        {rows.length === 0 ? (
          <EmptyState title="No forecast available">
            Train the model and materialize the grid, then reload — see the Data &amp; Pipeline page.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="ux4g-table w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500">
                  <th scope="col" className="py-2 pr-4">Horizon</th>
                  <th scope="col" className="py-2 pr-4">Valid at</th>
                  <th scope="col" className="py-2 pr-4">City mean PM2.5</th>
                  <th scope="col" className="py-2 pr-4">Peak cell</th>
                  <th scope="col" className="py-2">Category</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const band = pm25Band(r.mean);
                  return (
                    <tr key={r.step} className="border-b border-neutral-200/70">
                      <td className="py-2 pr-4 font-mono text-gov-700">+{r.step}h</td>
                      <td className="py-2 pr-4 text-neutral-600">
                        {new Date(r.timestep).toLocaleString()}
                      </td>
                      <td className="py-2 pr-4 tabular-nums">{r.mean.toFixed(0)} µg/m³</td>
                      <td className="py-2 pr-4 tabular-nums text-neutral-700">
                        {r.max.toFixed(0)} µg/m³
                      </td>
                      <td className="py-2">
                        <span className="flex items-center gap-1.5">
                          <span
                            aria-hidden="true"
                            className="h-2 w-2 rounded-full"
                            style={{ backgroundColor: band.color }}
                          />
                          {band.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card className="mt-6">
        <CardTitle
          actions={cellForecast && <Badge tone="sky">cell {cellForecast.grid_id}</Badge>}
        >
          Cell drill-down
        </CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          {hotCells.map((c) => (
            <button
              key={c.grid_id}
              onClick={() => loadCell(c.grid_id)}
              className={`ux4g-btn ux4g-btn-sm rounded-md px-2.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-gov-400 ${
                selectedGridId === c.grid_id ? "ux4g-btn-primary" : "ux4g-btn-outline-neutral"
              }`}
            >
              cell {c.grid_id} · {c.value.toFixed(0)} µg/m³
            </button>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const id = Number(new FormData(e.currentTarget).get("gridId"));
              if (Number.isFinite(id) && id > 0) loadCell(id);
            }}
            className="flex items-center gap-1.5"
          >
            <input
              name="gridId"
              type="number"
              min={1}
              placeholder="Grid ID"
              aria-label="Grid cell ID"
              className="w-24 rounded-md border border-neutral-300 px-2 py-1 text-xs outline-none focus-visible:ring-2 focus-visible:ring-gov-400"
            />
            <button
              type="submit"
              className="ux4g-btn ux4g-btn-outline-neutral ux4g-btn-sm rounded-md px-2.5 text-xs"
            >
              Load
            </button>
          </form>
        </div>

        {cellLoading ? (
          <Skeleton className="mt-4 h-72" />
        ) : cellForecast ? (
          <div className="mt-4">
            <p className="text-xs text-neutral-500">
              Last observed{" "}
              {cellForecast.last_observed_pm25 !== null
                ? `${cellForecast.last_observed_pm25.toFixed(0)} µg/m³`
                : "unavailable"}{" "}
              · generated from {new Date(cellForecast.generated_from).toLocaleString()}
            </p>
            <CellForecastChart data={cellChartData} />
          </div>
        ) : (
          hotCells.length > 0 && (
            <p className="mt-3 text-sm text-neutral-500">
              Pick a cell above to see its observed history and forecast trend.
            </p>
          )
        )}
      </Card>

      <div className="mt-6">
        <PlannedNote>
          Per-cell drill-down trend charts are now live above. Per-ward aggregation,
          uncertainty (p10/p90) bands, and meteorology-driven scenario toggles (wind shift,
          rain washout) remain planned — they need model/backend changes beyond what
          <code className="mx-1 rounded bg-neutral-100 px-1 py-0.5 text-xs">/forecast/cell</code>
          exposes today.
        </PlannedNote>
      </div>
    </>
  );
}
