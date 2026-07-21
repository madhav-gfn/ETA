"use client";

import type { TrackedAgentRun } from "@/lib/api";

/**
 * Print-only evidence document for one enforcement run — hidden on screen
 * (`hidden print:block`) and revealed exclusively when the page is printed /
 * saved as PDF (see the "Print evidence pack" button in EnforcementPanel and
 * the `.evidence-pack` rule in app/globals.css). No backend PDF generation —
 * this is the browser's native print-to-PDF over a purpose-built layout.
 */
export default function EvidencePack({ run }: { run: TrackedAgentRun | null }) {
  if (!run) return null;

  return (
    <div className="evidence-pack hidden p-8 text-sm text-black print:block">
      <h1 className="text-xl font-bold">Enforcement Evidence Pack — Run #{run.run_id}</h1>
      <p className="mt-1 text-xs text-neutral-600">
        Generated {new Date().toLocaleString()} · UrbanAir Intel (Government of India —
        prototype). Data is indicative; verify with official CPCB bulletins before legal
        or enforcement action.
      </p>

      <hr className="my-4 border-neutral-300" />

      <section className="mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide">Alert</h2>
        <p className="mt-1">
          PM2.5 {run.alert.forecast_value.toFixed(0)} µg/m³ at cell {run.alert.grid_id}{" "}
          (threshold {run.alert.threshold} µg/m³)
        </p>
        <p>Observed at {new Date(run.alert.timestamp).toLocaleString()}</p>
        <p>
          Location: {run.alert.centroid_lat.toFixed(4)}, {run.alert.centroid_lon.toFixed(4)}
        </p>
        {run.alert.synthetic && (
          <p className="italic">Synthetic drill — for demonstration only.</p>
        )}
      </section>

      <section className="mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide">Source attribution</h2>
        <p className="mt-1 capitalize">
          {run.attribution.source_category.replace(/_/g, " ")} — confidence{" "}
          {(run.attribution.confidence * 100).toFixed(0)}%
          {run.attribution.llm_used ? " (LLM rationale)" : " (deterministic)"}
        </p>
        <p className="mt-1">{run.attribution.rationale}</p>
        {run.attribution.evidence.length > 0 && (
          <ul className="mt-1 list-disc pl-5">
            {run.attribution.evidence.map((e, i) => (
              <li key={i}>{e.description}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide">
          Patrol route — {run.plan.route_summary}
        </h2>
        <ol className="mt-1 list-decimal pl-5">
          {run.plan.ranked_cells.map((s) => (
            <li key={s.grid_id}>
              Cell {s.grid_id} — {s.reason}
            </li>
          ))}
        </ol>
        <p className="mt-1">{run.plan.rationale}</p>
      </section>

      <section className="mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide">
          Dispatch &amp; outcome log
        </h2>
        <table className="mt-1 w-full border-collapse text-xs">
          <tbody>
            <tr className="border-b border-neutral-200">
              <td className="py-1 pr-4 font-medium">Status</td>
              <td className="py-1 capitalize">{run.status}</td>
            </tr>
            {run.assigned_to && (
              <tr className="border-b border-neutral-200">
                <td className="py-1 pr-4 font-medium">Assigned to</td>
                <td className="py-1">{run.assigned_to}</td>
              </tr>
            )}
            <tr className="border-b border-neutral-200">
              <td className="py-1 pr-4 font-medium">Signal detected</td>
              <td className="py-1">{new Date(run.completed_at).toLocaleString()}</td>
            </tr>
            {run.dispatched_at && (
              <tr className="border-b border-neutral-200">
                <td className="py-1 pr-4 font-medium">Dispatched</td>
                <td className="py-1">{new Date(run.dispatched_at).toLocaleString()}</td>
              </tr>
            )}
            {run.inspected_at && (
              <tr className="border-b border-neutral-200">
                <td className="py-1 pr-4 font-medium">Inspected</td>
                <td className="py-1">{new Date(run.inspected_at).toLocaleString()}</td>
              </tr>
            )}
            {run.closed_at && (
              <tr className="border-b border-neutral-200">
                <td className="py-1 pr-4 font-medium">Closed</td>
                <td className="py-1">{new Date(run.closed_at).toLocaleString()}</td>
              </tr>
            )}
            {run.signal_to_dispatch_minutes !== null && (
              <tr>
                <td className="py-1 pr-4 font-medium">Signal → dispatch</td>
                <td className="py-1">{run.signal_to_dispatch_minutes.toFixed(0)} minutes</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
