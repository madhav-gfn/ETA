"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import AdvisoryCard from "@/components/AdvisoryCard";
import {
  getForecastMetrics,
  getGridReadings,
  getRecommendations,
  type AgentRun,
  type ForecastMetrics,
  type GridReadingsResponse,
} from "@/lib/api";
import { pm25Band } from "@/lib/aqi";
import CountUp from "@/components/fx/CountUp";
import Reveal from "@/components/fx/Reveal";
import { Badge, Card, CardTitle, EmptyState, PageHeader, Skeleton, StatCard } from "@/components/ui";

export default function OverviewPage() {
  const [readings, setReadings] = useState<GridReadingsResponse | null>(null);
  const [metrics, setMetrics] = useState<ForecastMetrics | null>(null);
  const [lastRun, setLastRun] = useState<AgentRun | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      getGridReadings().then(setReadings),
      getForecastMetrics().then(setMetrics),
      getRecommendations().then((d) => d.runs.length > 0 && setLastRun(d.runs[0])),
    ]).finally(() => setLoading(false));
  }, []);

  const stats = useMemo(() => {
    if (!readings || readings.readings.length === 0) return null;
    const values = readings.readings.map((r) => r.value);
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const max = Math.max(...values);
    return { mean, max, cells: values.length };
  }, [readings]);

  const band = stats ? pm25Band(stats.mean) : null;

  return (
    <>
      <PageHeader
        title={
          <>
            City Overview <span className="gradient-text">· Delhi NCR</span>
          </>
        }
        subtitle="Live 1 km digital twin of the airshed — current state, forecast skill, and the latest agent-driven intervention at a glance."
        actions={
          <Link
            href="/map"
            className="ux4g-btn ux4g-btn-primary ux4g-btn-md rounded-lg px-4 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-gov-400"
          >
            Open live map →
          </Link>
        }
      />

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="City mean PM2.5"
            value={stats ? <CountUp value={stats.mean} /> : "—"}
            unit="µg/m³"
            accent={band ? "" : "text-neutral-500"}
            hint={
              band && (
                <span className="flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: band.color }}
                  />
                  {band.label}
                </span>
              )
            }
          />
          <StatCard
            label="Peak cell PM2.5"
            value={stats ? <CountUp value={stats.max} /> : "—"}
            unit="µg/m³"
            hint={stats ? `across ${stats.cells} grid cells` : "no gridded snapshot yet"}
          />
          <StatCard
            label="24h forecast RMSE"
            value={metrics?.model_rmse_24h ?? metrics?.model_rmse_1h ?? "—"}
            unit="µg/m³"
            hint={
              metrics ? (
                metrics.beats_persistence_24h ?? metrics.beats_persistence ? (
                  <span className="text-emerald-700">
                    beats persistence ({metrics.persistence_rmse_24h ?? metrics.persistence_rmse_1h})
                  </span>
                ) : (
                  <span className="text-amber-700">baseline ahead</span>
                )
              ) : (
                "model not trained yet"
              )
            }
          />
          <StatCard
            label="Snapshot time"
            value={
              readings?.measured_at
                ? new Date(readings.measured_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "—"
            }
            hint={
              readings?.measured_at
                ? new Date(readings.measured_at).toLocaleDateString()
                : "run the ingestion + grid pipeline"
            }
          />
        </div>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Reveal delay={0.1}>
          <AdvisoryCard />
        </Reveal>

        <Reveal delay={0.2}>
        <Card>
          <CardTitle
            actions={
              <Link
                href="/enforcement"
                className="text-xs text-gov-600 outline-none hover:text-gov-700 focus-visible:ring-2 focus-visible:ring-gov-500"
              >
                All runs →
              </Link>
            }
          >
            Latest intervention
          </CardTitle>
          {lastRun ? (
            <div className="flex flex-col gap-2 text-sm">
              <p className="text-neutral-800">
                PM2.5 {lastRun.alert.forecast_value.toFixed(0)} µg/m³ anomaly at cell{" "}
                {lastRun.alert.grid_id}{" "}
                {lastRun.alert.synthetic && <Badge tone="amber">drill</Badge>}
              </p>
              <p className="text-neutral-600">
                Attributed to{" "}
                <span className="font-medium capitalize text-saffron-600">
                  {lastRun.attribution.source_category.replace(/_/g, " ")}
                </span>{" "}
                ({(lastRun.attribution.confidence * 100).toFixed(0)}% confidence) —{" "}
                {lastRun.plan.route_summary}.
              </p>
              <p className="text-xs text-neutral-500">
                Completed {new Date(lastRun.completed_at).toLocaleString()}
              </p>
            </div>
          ) : (
            <EmptyState title="No agent runs yet">
              Trigger the monitoring → attribution → enforcement pipeline from the{" "}
              <Link href="/enforcement" className="text-gov-600 underline">
                Enforcement
              </Link>{" "}
              page.
            </EmptyState>
          )}
        </Card>
        </Reveal>
      </div>
    </>
  );
}
