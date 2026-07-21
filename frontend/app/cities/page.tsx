"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getCities, type CityHeadline } from "@/lib/api";
import { CITIES, pm25Band } from "@/lib/aqi";
import { Badge, Card, CardTitle, EmptyState, PageHeader, PlannedNote, Skeleton } from "@/components/ui";

export default function CitiesPage() {
  const [cities, setCities] = useState<CityHeadline[] | null>(null);

  useEffect(() => {
    getCities()
      .then((d) => setCities(d.cities))
      .catch(() => setCities([]));
  }, []);

  // Cities with a materialized snapshot, ranked worst-to-best mean PM2.5.
  const ranked = useMemo(() => {
    if (!cities) return [];
    return cities
      .filter((c) => c.measured_at !== null && c.mean_pm25 !== null)
      .sort((a, b) => (b.mean_pm25 ?? 0) - (a.mean_pm25 ?? 0));
  }, [cities]);

  const backendBySlug = useMemo(
    () => new Map((cities ?? []).map((c) => [c.city_slug, c])),
    [cities]
  );

  return (
    <>
      <PageHeader
        title="Multi-City Intelligence"
        subtitle="Compare air quality trends, intervention effectiveness, and compliance metrics across urban centres — learn from what worked in comparable cities."
      />

      <Card>
        <CardTitle>City ranking — mean PM2.5</CardTitle>
        {cities === null ? (
          <Skeleton className="h-32" />
        ) : ranked.length === 0 ? (
          <EmptyState title="No city data yet">
            Materialize a grid snapshot for at least one city to populate the ranking.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="ux4g-table w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500">
                  <th scope="col" className="py-2 pr-4">Rank</th>
                  <th scope="col" className="py-2 pr-4">City</th>
                  <th scope="col" className="py-2 pr-4">Mean PM2.5</th>
                  <th scope="col" className="py-2 pr-4">Peak</th>
                  <th scope="col" className="py-2 pr-4">Category</th>
                  <th scope="col" className="py-2 pr-4">Cells reporting</th>
                  <th scope="col" className="py-2">Model</th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((c, i) => {
                  const band = c.mean_pm25 !== null ? pm25Band(c.mean_pm25) : null;
                  return (
                    <tr key={c.city_slug} className="border-b border-neutral-200/70">
                      <td className="py-2 pr-4 font-mono text-neutral-500">{i + 1}</td>
                      <td className="py-2 pr-4 font-medium text-neutral-800">{c.display_name}</td>
                      <td className="py-2 pr-4 tabular-nums">
                        {c.mean_pm25 !== null ? c.mean_pm25.toFixed(0) : "—"} µg/m³
                      </td>
                      <td className="py-2 pr-4 tabular-nums text-neutral-700">
                        {c.max_pm25 !== null ? c.max_pm25.toFixed(0) : "—"} µg/m³
                      </td>
                      <td className="py-2 pr-4">
                        {band && (
                          <span className="flex items-center gap-1.5">
                            <span
                              aria-hidden="true"
                              className="h-2 w-2 rounded-full"
                              style={{ backgroundColor: band.color }}
                            />
                            {band.label}
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-4 tabular-nums">{c.cells_reporting}</td>
                      <td className="py-2">
                        <Badge tone={c.model_available ? "emerald" : "slate"}>
                          {c.model_available ? "trained" : "not trained"}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {CITIES.map((city) => {
          const backend = backendBySlug.get(city.slug);
          const live = backend?.live ?? false;
          return (
            <Card key={city.slug} className={live ? "" : "opacity-60"}>
              <div className="flex items-start justify-between">
                <h2 className="text-lg font-semibold text-neutral-900">{city.name}</h2>
                {live ? <Badge tone="emerald">live</Badge> : <Badge>onboarding planned</Badge>}
              </div>
              {live && backend ? (
                <>
                  <p className="mt-2 text-2xl font-semibold tabular-nums">
                    {backend.mean_pm25 !== null ? backend.mean_pm25.toFixed(0) : "—"}
                    <span className="ml-1 text-sm font-normal text-neutral-600">µg/m³ PM2.5</span>
                  </p>
                  {backend.mean_pm25 !== null && (
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-neutral-600">
                      <span
                        aria-hidden="true"
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: pm25Band(backend.mean_pm25).color }}
                      />
                      {pm25Band(backend.mean_pm25).label}
                    </p>
                  )}
                  <Link
                    href="/"
                    className="mt-3 inline-block text-xs text-gov-600 outline-none hover:text-gov-700 focus-visible:ring-2 focus-visible:ring-gov-500"
                  >
                    Open dashboard →
                  </Link>
                </>
              ) : (
                <p className="mt-2 text-sm text-neutral-500">
                  {backend
                    ? "Registered in the pipeline, but no gridded snapshot or trained model yet."
                    : "The pipeline is city-agnostic (OpenAQ + OSM + FIRMS cover all Indian " +
                      "metros); onboarding needs a grid definition and model training run."}
                </p>
              )}
            </Card>
          );
        })}
      </div>

      <div className="mt-6">
        <PlannedNote>
          Intervention-effectiveness comparison and NCAP compliance tracking are planned
          once ≥2 cities have enough operating history to compare.
        </PlannedNote>
      </div>
    </>
  );
}
