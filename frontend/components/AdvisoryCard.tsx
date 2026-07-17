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
    <section className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Citizen Health Advisory
        </h2>
        <div className="flex overflow-hidden rounded-md border border-slate-700 text-xs">
          {(["en", "hi"] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={`px-3 py-1 ${
                lang === l ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-400"
              }`}
            >
              {l === "en" ? "English" : "हिन्दी"}
            </button>
          ))}
        </div>
      </div>
      {loading && <p className="text-sm text-slate-500">Generating advisory…</p>}
      {!loading && data?.advisory && (
        <>
          <div className="flex items-center gap-3">
            <span className="rounded bg-slate-800 px-2 py-1 font-mono text-lg text-amber-300">
              {data.mean_pm25?.toFixed(0)} µg/m³
            </span>
            <span className="text-sm text-slate-400">
              {data.category} · peak {data.max_pm25?.toFixed(0)} µg/m³
              {data.llm_used ? " · AI-generated" : ""}
            </span>
          </div>
          <p className="text-sm leading-relaxed text-slate-200">{data.advisory}</p>
        </>
      )}
      {!loading && !data?.advisory && (
        <p className="text-sm text-slate-500">No gridded readings yet — advisory unavailable.</p>
      )}
    </section>
  );
}
