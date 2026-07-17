"use client";

import type { AgentRun } from "@/lib/api";

export default function EnforcementPanel({
  run,
  onDrill,
  drillRunning,
}: {
  run: AgentRun | null;
  onDrill: () => void;
  drillRunning: boolean;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Enforcement Intelligence
        </h2>
        <button
          onClick={onDrill}
          disabled={drillRunning}
          className="rounded-md bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-500 disabled:opacity-50"
        >
          {drillRunning ? "Running agents…" : "Run anomaly drill"}
        </button>
      </div>

      {!run && (
        <p className="text-sm text-slate-500">
          No agent runs yet. Trigger the anomaly drill to watch the monitoring →
          attribution → enforcement pipeline execute.
        </p>
      )}

      {run && (
        <div className="flex flex-col gap-3 text-sm">
          <div className="rounded-md border border-rose-900/60 bg-rose-950/30 p-3">
            <p className="font-medium text-rose-300">
              ⚠ PM2.5 {run.alert.forecast_value.toFixed(0)} µg/m³ at cell {run.alert.grid_id}
              {run.alert.synthetic && (
                <span className="ml-2 rounded bg-slate-700 px-1.5 py-0.5 text-[10px] uppercase">
                  synthetic drill
                </span>
              )}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              threshold {run.alert.threshold} µg/m³ · {new Date(run.alert.timestamp).toLocaleString()}
            </p>
          </div>

          <div className="rounded-md border border-slate-800 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">Source attribution</p>
            <p className="mt-1">
              <span className="font-semibold capitalize text-amber-300">
                {run.attribution.source_category.replace("_", " ")}
              </span>{" "}
              <span className="text-slate-400">
                (confidence {(run.attribution.confidence * 100).toFixed(0)}%
                {run.attribution.llm_used ? ", LLM rationale" : ", deterministic"})
              </span>
            </p>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">{run.attribution.rationale}</p>
            {run.attribution.evidence.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1">
                {run.attribution.evidence.map((e, i) => (
                  <li key={i} className="text-xs text-slate-400">
                    • {e.description}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-md border border-slate-800 p-3">
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Patrol route · {run.plan.route_summary}
            </p>
            <ol className="mt-2 flex flex-col gap-1">
              {run.plan.ranked_cells.map((s, i) => (
                <li key={s.grid_id} className="text-xs text-slate-300">
                  <span className="font-mono text-sky-400">{i + 1}.</span> cell {s.grid_id} — {s.reason}
                </li>
              ))}
            </ol>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">{run.plan.rationale}</p>
          </div>
        </div>
      )}
    </section>
  );
}
