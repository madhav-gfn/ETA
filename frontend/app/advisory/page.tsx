"use client";

import { useEffect, useState } from "react";
import { getAdvisory, type AdvisoryResponse } from "@/lib/api";
import { AQI_BANDS, LANGS } from "@/lib/aqi";
import {
  Badge,
  Card,
  CardTitle,
  EmptyState,
  PageHeader,
  PlannedNote,
  Skeleton,
} from "@/components/ui";

export default function AdvisoryPage() {
  const [lang, setLang] = useState<"en" | "hi">("en");
  const [data, setData] = useState<AdvisoryResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getAdvisory("delhi-ncr", lang)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [lang]);

  return (
    <>
      <PageHeader
        title="Citizen Health Advisory"
        subtitle="LLM-generated, ward-aware health advisories in regional languages — pushable to mobile apps, public displays, and IVR."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle
            actions={
              <div
                role="radiogroup"
                aria-label="Advisory language"
                className="flex flex-wrap gap-1"
              >
                {LANGS.map((l) => (
                  <button
                    key={l.code}
                    role="radio"
                    aria-checked={lang === l.code}
                    disabled={!l.live}
                    title={l.live ? l.label : `${l.label} — coming soon`}
                    onClick={() => l.live && setLang(l.code as "en" | "hi")}
                    className={`ux4g-btn ux4g-btn-xs rounded-md px-2.5 text-xs outline-none focus-visible:ring-2 focus-visible:ring-gov-400 ${
                      lang === l.code
                        ? "ux4g-btn-primary"
                        : l.live
                          ? "ux4g-btn-outline-neutral"
                          : "ux4g-btn-outline-neutral cursor-not-allowed opacity-50"
                    }`}
                  >
                    {l.native}
                  </button>
                ))}
              </div>
            }
          >
            Current advisory
          </CardTitle>

          {loading ? (
            <Skeleton className="h-32" />
          ) : data?.advisory ? (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-lg bg-neutral-100 px-3 py-1.5 font-mono text-xl text-saffron-600">
                  {data.mean_pm25?.toFixed(0)} µg/m³
                </span>
                <span className="text-sm text-neutral-600">
                  {data.category} · peak {data.max_pm25?.toFixed(0)} µg/m³
                </span>
                {data.llm_used && <Badge tone="sky">AI-generated</Badge>}
              </div>
              <p lang={lang} className="text-base leading-relaxed text-neutral-900">
                {data.advisory}
              </p>
              {data.measured_at && (
                <p className="text-xs text-neutral-500">
                  Based on snapshot {new Date(data.measured_at).toLocaleString()}
                </p>
              )}
            </div>
          ) : (
            <EmptyState title="Advisory unavailable">
              No gridded readings yet — run the ingestion pipeline (see Data &amp; Pipeline).
            </EmptyState>
          )}
        </Card>

        <Card>
          <CardTitle>Health guidance by band</CardTitle>
          <ul className="flex flex-col gap-2">
            {AQI_BANDS.map((b) => (
              <li key={b.label} className="flex gap-2.5 text-xs">
                <span
                  aria-hidden="true"
                  className="mt-0.5 h-3 w-3 shrink-0 rounded-sm"
                  style={{ backgroundColor: b.color }}
                />
                <span>
                  <span className="font-medium text-neutral-800">{b.label}</span>{" "}
                  <span className="text-neutral-400">
                    ({b.max === Infinity ? "250+" : `≤${b.max}`} µg/m³)
                  </span>
                  <span className="block text-neutral-600">{b.guidance}</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="mt-6">
        <PlannedNote>
          Push channels (SMS/IVR/app notifications), vulnerability mapping (schools,
          hospitals, outdoor-worker zones vs forecast AQI), and per-ward subscription
          preferences are planned — the remaining four languages activate once the backend
          advisory endpoint accepts them.
        </PlannedNote>
      </div>
    </>
  );
}
