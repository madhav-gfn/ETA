"use client";

import { useEffect, useState } from "react";
import {
  getGridCells,
  getGridReadings,
  getHealth,
  getIngestionSummary,
  type IngestionSourceSummary,
} from "@/lib/api";
import { Badge, Card, CardTitle, PageHeader, PlannedNote, Skeleton } from "@/components/ui";

// Descriptive copy per backend source key (backend/app/ingestion/ingestion.py
// SOURCE_TABLES) — merged with the live rows from GET /ingestion/summary.
const SOURCE_META: Record<string, { name: string; via: string; role: string; cadence: string }> = {
  caaqms: {
    name: "CAAQMS ground sensors",
    via: "OpenAQ v3 API",
    role: "Hourly PM2.5/PM10/NO₂ station readings — the ground truth layer.",
    cadence: "hourly",
  },
  sentinel5p: {
    name: "Sentinel-5P satellite",
    via: "Copernicus / TROPOMI",
    role: "NO₂ and aerosol column densities for area-wide coverage between stations.",
    cadence: "daily",
  },
  firms: {
    name: "NASA FIRMS",
    via: "FIRMS API",
    role: "Thermal anomalies — fire and waste-burning detection for attribution.",
    cadence: "near-real-time",
  },
  osm: {
    name: "OSM land use",
    via: "Overpass API (mirrored, tiled)",
    role: "Roads, industrial zones, construction — static context for source attribution.",
    cadence: "on demand",
  },
  meteo: {
    name: "Meteorological forecast",
    via: "Open-Meteo",
    role: "Wind, temperature, humidity, boundary-layer inputs to the forecast model.",
    cadence: "hourly",
  },
};

const RUN_STATUS_TONE = {
  success: "emerald",
  failed: "rose",
  running: "amber",
} as const;

export default function DataPage() {
  const [apiUp, setApiUp] = useState<boolean | null>(null);
  const [cellCount, setCellCount] = useState<number | null>(null);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [sources, setSources] = useState<IngestionSourceSummary[] | null>(null);

  useEffect(() => {
    getHealth().then(() => setApiUp(true)).catch(() => setApiUp(false));
    getGridCells().then((d) => setCellCount(d.cell_count)).catch(() => {});
    getGridReadings().then((d) => setSnapshot(d.measured_at)).catch(() => {});
    getIngestionSummary().then((d) => setSources(d.sources)).catch(() => setSources([]));
  }, []);

  return (
    <>
      <PageHeader
        title="Data & Pipeline"
        subtitle="What feeds the digital twin: five fused data sources, a 1 km PostGIS grid, and the ConvLSTM feature cube."
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardTitle>API</CardTitle>
          {apiUp === null ? (
            <p className="text-sm text-neutral-500">checking…</p>
          ) : apiUp ? (
            <Badge tone="emerald">reachable</Badge>
          ) : (
            <Badge tone="rose">offline</Badge>
          )}
        </Card>
        <Card>
          <CardTitle>Grid cells</CardTitle>
          <p className="text-2xl font-semibold tabular-nums">{cellCount ?? "—"}</p>
          <p className="text-xs text-neutral-500">1 km × 1 km, Delhi NCR</p>
        </Card>
        <Card>
          <CardTitle>Last materialized snapshot</CardTitle>
          <p className="text-sm text-neutral-800">
            {snapshot ? new Date(snapshot).toLocaleString() : "none yet"}
          </p>
        </Card>
      </div>

      <Card className="mt-6">
        <CardTitle>Fused data sources</CardTitle>
        {sources === null ? (
          <Skeleton className="h-40" />
        ) : (
          <div className="overflow-x-auto">
            <table className="ux4g-table w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500">
                  <th scope="col" className="py-2 pr-4">Source</th>
                  <th scope="col" className="py-2 pr-4">Via</th>
                  <th scope="col" className="py-2 pr-4">Role</th>
                  <th scope="col" className="py-2 pr-4">Cadence</th>
                  <th scope="col" className="py-2 pr-4">Rows</th>
                  <th scope="col" className="py-2 pr-4">Last data</th>
                  <th scope="col" className="py-2">Last run</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => {
                  const meta = SOURCE_META[s.source] ?? {
                    name: s.source,
                    via: "—",
                    role: "—",
                    cadence: "—",
                  };
                  const runTone = s.last_run
                    ? RUN_STATUS_TONE[s.last_run.status as keyof typeof RUN_STATUS_TONE] ?? "slate"
                    : "slate";
                  return (
                    <tr key={s.source} className="border-b border-neutral-200/70 align-top">
                      <td className="py-2.5 pr-4 font-medium text-neutral-800">{meta.name}</td>
                      <td className="py-2.5 pr-4 text-neutral-600">{meta.via}</td>
                      <td className="py-2.5 pr-4 text-neutral-600">{meta.role}</td>
                      <td className="py-2.5 pr-4">
                        <Badge tone="sky">{meta.cadence}</Badge>
                      </td>
                      <td className="py-2.5 pr-4 tabular-nums text-neutral-700">{s.table_rows}</td>
                      <td className="py-2.5 pr-4 text-neutral-600">
                        {s.latest_data_at ? new Date(s.latest_data_at).toLocaleString() : "no data yet"}
                      </td>
                      <td className="py-2.5">
                        {s.last_run ? (
                          <div className="flex flex-col gap-0.5">
                            <Badge tone={runTone}>
                              {s.last_run.status}
                              {s.last_run.status === "success" ? ` · ${s.last_run.records_ingested}` : ""}
                            </Badge>
                            {s.last_run.status === "failed" && s.last_run.error_message && (
                              <span className="text-[11px] text-rose-600">{s.last_run.error_message}</span>
                            )}
                          </div>
                        ) : (
                          <Badge>never run</Badge>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="mt-6">
        <PlannedNote>
          Manual, auth-gated re-ingestion buttons remain planned — the endpoints exist but
          need an auth layer before exposing them in the UI, since each pull hits a
          rate-limited external API.
        </PlannedNote>
      </div>
    </>
  );
}
