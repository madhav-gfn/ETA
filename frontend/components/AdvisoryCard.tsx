"use client";

import { useEffect, useState } from "react";
import { getAdvisory, type AdvisoryResponse } from "@/lib/api";

export default function AdvisoryCard() {
  const [lang, setLang] = useState<"en" | "hi">("en");
  const [data, setData] = useState<AdvisoryResponse | null>(null);
  const [loading, setLoading] = useState(false);

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
    <section className="ux4g-card glass-card flex flex-col gap-3 rounded-xl border border-neutral-200 p-4">
      <div className="flex items-center justify-between">
        <h2 className="ux4g-card-title text-sm font-semibold uppercase tracking-wide text-neutral-700">
          Citizen Health Advisory
        </h2>
        <div className="flex gap-1 text-xs" role="radiogroup" aria-label="Advisory language">
          {(["en", "hi"] as const).map((l) => (
            <button
              key={l}
              role="radio"
              aria-checked={lang === l}
              onClick={() => setLang(l)}
              className={`ux4g-btn ux4g-btn-xs rounded-md px-3 outline-none focus-visible:ring-2 focus-visible:ring-gov-400 ${
                lang === l ? "ux4g-btn-primary" : "ux4g-btn-outline-neutral"
              }`}
            >
              {l === "en" ? "English" : "हिन्दी"}
            </button>
          ))}
        </div>
      </div>
      {loading && <p className="text-sm text-neutral-500">Generating advisory…</p>}
      {!loading && data?.advisory && (
        <>
          <div className="flex items-center gap-3">
            <span className="rounded bg-neutral-100 px-2 py-1 font-mono text-lg text-saffron-600">
              {data.mean_pm25?.toFixed(0)} µg/m³
            </span>
            <span className="text-sm text-neutral-600">
              {data.category} · peak {data.max_pm25?.toFixed(0)} µg/m³
              {data.llm_used ? " · AI-generated" : ""}
            </span>
          </div>
          <p className="text-sm leading-relaxed text-neutral-800">{data.advisory}</p>
        </>
      )}
      {!loading && !data?.advisory && (
        <p className="text-sm text-neutral-500">No gridded readings yet — advisory unavailable.</p>
      )}
    </section>
  );
}
