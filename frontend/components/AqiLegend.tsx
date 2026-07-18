import { AQI_BANDS } from "@/lib/aqi";

export default function AqiLegend() {
  return (
    <div aria-label="PM2.5 color legend" className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-neutral-600">
      <span className="font-medium uppercase tracking-wide text-neutral-500">PM2.5 µg/m³</span>
      {AQI_BANDS.map((b, i) => (
        <span key={b.label} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: b.color }}
          />
          {b.label}
          <span className="text-neutral-400">
            {b.max === Infinity ? "250+" : `≤${b.max}`}
          </span>
        </span>
      ))}
    </div>
  );
}
