"use client";

import { useEffect, useState } from "react";
import { getGridCells, getGridReadings, getHealth } from "@/lib/api";
import { Badge, Card, CardTitle, PageHeader, PlannedNote } from "@/components/ui";

const SOURCES = [
  {
    name: "CAAQMS ground sensors",
    via: "OpenAQ v3 API",
    role: "Hourly PM2.5/PM10/NO₂ station readings — the ground truth layer.",
    cadence: "hourly",
  },
  {
    name: "Sentinel-5P satellite",
    via: "Copernicus / TROPOMI",
    role: "NO₂ and aerosol column densities for area-wide coverage between stations.",
    cadence: "daily",
  },
  {
    name: "NASA FIRMS",
    via: "FIRMS API",
    role: "Thermal anomalies — fire and waste-burning detection for attribution.",
    cadence: "near-real-time",
  },
  {
    name: "OSM land use",
    via: "Overpass API (mirrored, tiled)",
    role: "Roads, industrial zones, construction — static context for source attribution.",
    cadence: "on demand",
  },
  {
    name: "Meteorological forecast",
    via: "Open-Meteo",
    role: "Wind, temperature, humidity, boundary-layer inputs to the forecast model.",
    cadence: "hourly",
  },
];

export default function DataPage() {
  const [apiUp, setApiUp] = useState<boolean | null>(null);
  const [cellCount, setCellCount] = useState<number | null>(null);
  const [snapshot, setSnapshot] = useState<string | null>(null);

  useEffect(() => {
    getHealth().then(() => setApiUp(true)).catch(() => setApiUp(false));
    getGridCells().then((d) => setCellCount(d.cell_count)).catch(() => {});
    getGridReadings().then((d) => setSnapshot(d.measured_at)).catch(() => {});
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
        <div className="overflow-x-auto">
          <table className="ux4g-table w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500">
                <th scope="col" className="py-2 pr-4">Source</th>
                <th scope="col" className="py-2 pr-4">Via</th>
                <th scope="col" className="py-2 pr-4">Role</th>
                <th scope="col" className="py-2">Cadence</th>
              </tr>
            </thead>
            <tbody>
              {SOURCES.map((s) => (
                <tr key={s.name} className="border-b border-neutral-200/70 align-top">
                  <td className="py-2.5 pr-4 font-medium text-neutral-800">{s.name}</td>
                  <td className="py-2.5 pr-4 text-neutral-600">{s.via}</td>
                  <td className="py-2.5 pr-4 text-neutral-600">{s.role}</td>
                  <td className="py-2.5">
                    <Badge tone="sky">{s.cadence}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="mt-6">
        <PlannedNote>
          Per-source freshness timestamps and manual re-ingestion buttons need a backend
          ingestion-status endpoint (currently ingestion is POST-triggered per source with
          no consolidated status) — see SITEMAP.md.
        </PlannedNote>
      </div>
    </>
  );
}
