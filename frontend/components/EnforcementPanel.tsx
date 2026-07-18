"use client";

import { TriangleAlert } from "lucide-react";
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
    <section className="ux4g-card glass-card flex flex-col gap-3 rounded-xl border border-neutral-200 p-4">
      <div className="flex items-center justify-between">
        <h2 className="ux4g-card-title text-sm font-semibold uppercase tracking-wide text-neutral-700">
          Enforcement Intelligence
        </h2>
        <button
          onClick={onDrill}
          disabled={drillRunning}
          className="ux4g-btn ux4g-btn-danger ux4g-btn-sm rounded-md px-3 text-xs font-medium disabled:opacity-50"
        >
          {drillRunning ? "Running agents…" : "Run anomaly drill"}
        </button>
      </div>

      {!run && (
        <p className="text-sm text-neutral-500">
          No agent runs yet. Trigger the anomaly drill to watch the monitoring →
          attribution → enforcement pipeline execute.
        </p>
      )}

      {run && (
        <div className="flex flex-col gap-3 text-sm">
          <div className="rounded-md border border-rose-200 bg-rose-50 p-3">
            <p className="flex flex-wrap items-center gap-1.5 font-medium text-rose-700">
              <TriangleAlert aria-hidden="true" className="h-4 w-4 shrink-0" strokeWidth={2} />
              PM2.5 {run.alert.forecast_value.toFixed(0)} µg/m³ at cell {run.alert.grid_id}
              {run.alert.synthetic && (
                <span className="ml-2 rounded bg-neutral-200 px-1.5 py-0.5 text-[10px] uppercase">
                  synthetic drill
                </span>
              )}
            </p>
            <p className="mt-1 text-xs text-neutral-600">
              threshold {run.alert.threshold} µg/m³ · {new Date(run.alert.timestamp).toLocaleString()}
            </p>
          </div>

          <div className="rounded-md border border-neutral-200 p-3">
            <p className="text-xs uppercase tracking-wide text-neutral-500">Source attribution</p>
            <p className="mt-1">
              <span className="font-semibold capitalize text-saffron-600">
                {run.attribution.source_category.replace("_", " ")}
              </span>{" "}
              <span className="text-neutral-600">
                (confidence {(run.attribution.confidence * 100).toFixed(0)}%
                {run.attribution.llm_used ? ", LLM rationale" : ", deterministic"})
              </span>
            </p>
            <p className="mt-2 text-xs leading-relaxed text-neutral-700">{run.attribution.rationale}</p>
            {run.attribution.evidence.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1">
                {run.attribution.evidence.map((e, i) => (
                  <li key={i} className="text-xs text-neutral-600">
                    • {e.description}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-md border border-neutral-200 p-3">
            <p className="text-xs uppercase tracking-wide text-neutral-500">
              Patrol route · {run.plan.route_summary}
            </p>
            <ol className="mt-2 flex flex-col gap-1">
              {run.plan.ranked_cells.map((s, i) => (
                <li key={s.grid_id} className="text-xs text-neutral-700">
                  <span className="font-mono text-gov-600">{i + 1}.</span> cell {s.grid_id} — {s.reason}
                </li>
              ))}
            </ol>
            <p className="mt-2 text-xs leading-relaxed text-neutral-600">{run.plan.rationale}</p>
          </div>
        </div>
      )}
    </section>
  );
}
