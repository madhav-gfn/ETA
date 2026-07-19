"use client";

import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, Rectangle, Polyline, CircleMarker, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { AgentRun, ForecastResponse, GridCellInfo, GridReadingsResponse } from "@/lib/api";
import { pm25Color } from "@/lib/aqi";

// ~1km cell half-extent in degrees at Delhi latitude
const HALF_LAT = 0.0045;
const HALF_LON = 0.0051;

interface Props {
  cells: GridCellInfo[];
  readings: GridReadingsResponse | null;
  forecast: ForecastResponse | null;
  forecastStep: number | null; // null => show live readings
  agentRun: AgentRun | null;
  onCellClick?: (cell: GridCellInfo, value: number | null) => void;
}

export default function AqiMap({ cells, readings, forecast, forecastStep, agentRun, onCellClick }: Props) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const valueByGridId = useMemo(() => {
    const m = new Map<number, number>();
    if (forecastStep !== null && forecast) {
      const frame = forecast.horizons[String(forecastStep)];
      if (frame) {
        const byPos = new Map<string, number>();
        frame.pm25.forEach((row, r) => row.forEach((v, c) => byPos.set(`${r}:${c}`, v)));
        cells.forEach((cell) => {
          const v = byPos.get(`${cell.row_idx}:${cell.col_idx}`);
          const valid = forecast.valid_mask?.[cell.row_idx]?.[cell.col_idx];
          if (v !== undefined && valid) m.set(cell.grid_id, v);
        });
      }
    } else if (readings) {
      readings.readings.forEach((r) => m.set(r.grid_id, r.value));
    }
    return m;
  }, [cells, readings, forecast, forecastStep]);

  if (!mounted) return <div className="h-full w-full animate-pulse rounded-lg bg-neutral-100" />;

  const routeCells = agentRun?.plan.ranked_cells ?? [];

  return (
    <MapContainer
      center={[28.635, 77.1]}
      zoom={10}
      className="h-full w-full rounded-lg"
      preferCanvas
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> contributors'
        url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      />
      {cells.map((cell) => {
        const v = valueByGridId.get(cell.grid_id);
        if (v === undefined) return null;
        return (
          <Rectangle
            key={cell.grid_id}
            bounds={[
              [cell.centroid_lat - HALF_LAT, cell.centroid_lon - HALF_LON],
              [cell.centroid_lat + HALF_LAT, cell.centroid_lon + HALF_LON],
            ]}
            pathOptions={{ color: pm25Color(v), weight: 0, fillOpacity: 0.45 }}
            eventHandlers={{ click: () => onCellClick?.(cell, v) }}
          >
            <Tooltip sticky>
              cell {cell.grid_id}: PM2.5 {v.toFixed(0)} µg/m³
            </Tooltip>
          </Rectangle>
        );
      })}
      {agentRun && (
        <CircleMarker
          center={[agentRun.alert.centroid_lat, agentRun.alert.centroid_lon]}
          radius={12}
          pathOptions={{ color: "#f43f5e", weight: 3, fillOpacity: 0.2 }}
        >
          <Tooltip permanent direction="top">
            Anomaly · {agentRun.alert.forecast_value.toFixed(0)} µg/m³
            {agentRun.alert.synthetic ? " (drill)" : ""}
          </Tooltip>
        </CircleMarker>
      )}
      {routeCells.length > 1 && (
        <Polyline
          positions={routeCells.map((s) => [s.centroid_lat, s.centroid_lon] as [number, number])}
          pathOptions={{ color: "#38bdf8", weight: 3, dashArray: "6 6" }}
        />
      )}
      {routeCells.map((s, i) => (
        <CircleMarker
          key={s.grid_id}
          center={[s.centroid_lat, s.centroid_lon]}
          radius={8}
          pathOptions={{ color: "#38bdf8", fillColor: "#0ea5e9", fillOpacity: 0.9 }}
        >
          <Tooltip>
            stop {i + 1}: {s.reason}
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
