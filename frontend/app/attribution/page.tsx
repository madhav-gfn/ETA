"use client";

import {
  Car,
  Construction,
  Factory,
  Flame,
  HelpCircle,
  Wind,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { getRecommendations, type AgentRun } from "@/lib/api";
import {
  Badge,
  Card,
  CardTitle,
  EmptyState,
  PageHeader,
  PlannedNote,
  ProgressBar,
  Skeleton,
} from "@/components/ui";

const SOURCE_ICONS: Record<string, LucideIcon> = {
  traffic: Car,
  construction: Construction,
  industrial: Factory,
  waste_burning: Flame,
  fires: Flame,
  dust: Wind,
  unknown: HelpCircle,
};

export default function AttributionPage() {
  const [runs, setRuns] = useState<AgentRun[] | null>(null);

  useEffect(() => {
    getRecommendations()
      .then((d) => setRuns(d.runs))
      .catch(() => setRuns([]));
  }, []);

  return (
    <>
      <PageHeader
        title="Source Attribution"
        subtitle="Multi-modal agent evidence: spatial AQI patterns cross-referenced with OSM land use, FIRMS thermal anomalies, and Sentinel-5P columns — with confidence scores per attribution."
      />

      {runs === null ? (
        <Skeleton className="h-48" />
      ) : runs.length === 0 ? (
        <EmptyState title="No attributions yet">
          Attributions are produced when the agent pipeline investigates an anomaly. Run a
          drill from the Enforcement page to generate one.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-4">
          {runs.map((run, i) => {
            const a = run.attribution;
            const SourceIcon = SOURCE_ICONS[a.source_category] ?? HelpCircle;
            return (
              <Card key={i}>
                <CardTitle
                  actions={
                    <div className="flex gap-2">
                      {run.alert.synthetic && <Badge tone="amber">drill</Badge>}
                      <Badge tone={a.llm_used ? "sky" : "slate"}>
                        {a.llm_used ? "LLM rationale" : "deterministic"}
                      </Badge>
                    </div>
                  }
                >
                  Cell {run.alert.grid_id} · {new Date(run.completed_at).toLocaleString()}
                </CardTitle>

                <div className="flex flex-wrap items-center gap-4">
                  <p className="flex items-center gap-2 text-lg">
                    <span
                      aria-hidden="true"
                      className="grid h-8 w-8 place-items-center rounded-lg bg-saffron-50 text-saffron-600"
                    >
                      <SourceIcon className="h-[18px] w-[18px]" strokeWidth={1.75} />
                    </span>
                    <span className="font-semibold capitalize text-saffron-600">
                      {a.source_category.replace(/_/g, " ")}
                    </span>
                  </p>
                  <div className="flex items-center gap-2">
                    <ProgressBar
                      value={a.confidence * 100}
                      label={`Attribution confidence ${(a.confidence * 100).toFixed(0)} percent`}
                    />
                    <span className="text-sm tabular-nums text-neutral-700">
                      {(a.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                <p className="mt-3 text-sm leading-relaxed text-neutral-700">{a.rationale}</p>

                {a.evidence.length > 0 && (
                  <details className="mt-3 group">
                    <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-neutral-500 outline-none hover:text-neutral-700 focus-visible:ring-2 focus-visible:ring-gov-500">
                      Evidence ({a.evidence.length})
                    </summary>
                    <ul className="mt-2 flex flex-col gap-1.5">
                      {a.evidence.map((e, j) => (
                        <li key={j} className="rounded-lg bg-neutral-100 px-3 py-2 text-xs text-neutral-600">
                          <span className="mr-2 rounded bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] uppercase text-gov-600">
                            {e.kind}
                          </span>
                          {e.description}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </Card>
            );
          })}
        </div>
      )}

      <div className="mt-6">
        <PlannedNote>
          Ward-level attribution heatmap, comparison against CPCB emission inventories, and
          construction-permit / industrial-registry overlays are planned backend additions.
        </PlannedNote>
      </div>
    </>
  );
}
