"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getGridReadings, type GridReadingsResponse } from "@/lib/api";
import { CITIES, pm25Band } from "@/lib/aqi";
import { Badge, Card, PageHeader, PlannedNote } from "@/components/ui";

export default function CitiesPage() {
  const [readings, setReadings] = useState<GridReadingsResponse | null>(null);

  useEffect(() => {
    getGridReadings().then(setReadings).catch(() => {});
  }, []);

  const delhiMean = useMemo(() => {
    if (!readings || readings.readings.length === 0) return null;
    return readings.readings.reduce((a, r) => a + r.value, 0) / readings.readings.length;
  }, [readings]);

  return (
    <>
      <PageHeader
        title="Multi-City Intelligence"
        subtitle="Compare air quality trends, intervention effectiveness, and compliance metrics across urban centres — learn from what worked in comparable cities."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {CITIES.map((city) => {
          const band = city.live && delhiMean !== null ? pm25Band(delhiMean) : null;
          return (
            <Card
              key={city.slug}
              className={city.live ? "" : "opacity-60"}
            >
              <div className="flex items-start justify-between">
                <h2 className="text-lg font-semibold text-neutral-900">{city.name}</h2>
                {city.live ? (
                  <Badge tone="emerald">live</Badge>
                ) : (
                  <Badge>onboarding planned</Badge>
                )}
              </div>
              {city.live ? (
                <>
                  <p className="mt-2 text-2xl font-semibold tabular-nums">
                    {delhiMean !== null ? delhiMean.toFixed(0) : "—"}
                    <span className="ml-1 text-sm font-normal text-neutral-600">µg/m³ PM2.5</span>
                  </p>
                  {band && (
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-neutral-600">
                      <span
                        aria-hidden="true"
                        className="h-2 w-2 rounded-full"
                        style={{ backgroundColor: band.color }}
                      />
                      {band.label}
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
                  The pipeline is city-agnostic (OpenAQ + OSM + FIRMS cover all Indian
                  metros); onboarding needs a grid definition and model training run.
                </p>
              )}
            </Card>
          );
        })}
      </div>

      <div className="mt-6">
        <PlannedNote>
          Cross-city ranking table, intervention-effectiveness comparison, and NCAP
          compliance tracking are planned once ≥2 cities are onboarded. The backend already
          keys every table by city_slug.
        </PlannedNote>
      </div>
    </>
  );
}
