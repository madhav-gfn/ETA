import BackendStatus from "@/components/BackendStatus";

const steps = [
  { n: 1, label: "Project setup & architecture foundation", done: true },
  { n: 2, label: "Data ingestion layer (CAAQMS, FIRMS, OSM, Sentinel-5P)", done: true },
  { n: 3, label: "Geospatial grid engine (1km grid + IDW)", done: false },
  { n: 4, label: "Feature engineering & multi-modal fusion", done: false },
  { n: 5, label: "Hyperlocal predictive forecasting model", done: false },
  { n: 6, label: "Multi-agent intelligence layer", done: false },
  { n: 7, label: "City & citizen dashboard", done: false },
  { n: 8, label: "Integration, deployment & demo packaging", done: false },
];

export default function Home() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-8 px-6 py-16">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">UrbanAir Intel</h1>
        <p className="mt-2 text-slate-400">
          AI-powered Urban Air Quality Intelligence platform — dashboard placeholder.
          Replaced with the live map/forecast/agent UI in Step 7.
        </p>
      </div>

      <BackendStatus />

      <ol className="flex flex-col gap-2">
        {steps.map((step) => (
          <li
            key={step.n}
            className={`flex items-center gap-3 rounded-md border px-4 py-2 text-sm ${
              step.done
                ? "border-emerald-800 bg-emerald-950/40 text-emerald-300"
                : "border-slate-800 bg-slate-900/40 text-slate-400"
            }`}
          >
            <span className="font-mono text-xs">{step.done ? "✓" : step.n}</span>
            <span>{step.label}</span>
          </li>
        ))}
      </ol>
    </main>
  );
}
