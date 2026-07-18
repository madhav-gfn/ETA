"use client";

import { Info } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useRef, type MouseEvent, type ReactNode } from "react";

/** Glass card with a cursor-tracking spotlight glow. */
export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const onMove = useCallback((e: MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--spot-x", `${e.clientX - r.left}px`);
    el.style.setProperty("--spot-y", `${e.clientY - r.top}px`);
  }, []);

  return (
    <section
      ref={ref}
      onMouseMove={onMove}
      className={`ux4g-card glass-card rounded-xl border border-neutral-200 p-4 shadow-lg shadow-neutral-900/5 ${className}`}
    >
      {children}
    </section>
  );
}

export function CardTitle({
  children,
  actions,
}: {
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <h2 className="ux4g-card-title text-xs font-semibold uppercase tracking-widest text-neutral-600">
        {children}
      </h2>
      {actions}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  const pathname = usePathname();
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        {pathname !== "/" && (
          <nav aria-label="Breadcrumb" className="ux4g-breadcrumb ux4g-breadcrumb-divider mb-2">
            <ol className="flex items-center text-xs text-neutral-500">
              <li className="ux4g-breadcrumb-item">
                <Link
                  href="/"
                  className="text-gov-600 outline-none hover:text-gov-700 focus-visible:ring-2 focus-visible:ring-gov-500"
                >
                  Overview
                </Link>
              </li>
              <li className="ux4g-breadcrumb-item" aria-current="page">
                {typeof title === "string" ? title : "Current page"}
              </li>
            </ol>
          </nav>
        )}
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900 sm:text-3xl">
          {title}
        </h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-sm text-neutral-600">{subtitle}</p>}
      </div>
      {actions}
    </header>
  );
}

export function StatCard({
  label,
  value,
  unit,
  hint,
  accent = "text-neutral-900",
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
  accent?: string;
}) {
  return (
    <Card className="flex flex-col gap-1">
      <p className="text-[11px] font-medium uppercase tracking-widest text-neutral-500">{label}</p>
      <p className={`text-3xl font-semibold tabular-nums ${accent}`}>
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-neutral-600">{unit}</span>}
      </p>
      {hint && <p className="text-xs text-neutral-500">{hint}</p>}
    </Card>
  );
}

export function Badge({
  children,
  tone = "slate",
}: {
  children: ReactNode;
  tone?: "slate" | "sky" | "emerald" | "amber" | "rose";
}) {
  const tones = {
    slate: "bg-neutral-100 text-neutral-700 border-neutral-300",
    sky: "bg-gov-50 text-gov-700 border-gov-300",
    emerald: "bg-emerald-50 text-emerald-800 border-emerald-300",
    amber: "bg-saffron-50 text-saffron-700 border-saffron-300",
    rose: "bg-rose-50 text-rose-800 border-rose-300",
  } as const;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-lg bg-neutral-200 motion-reduce:animate-none ${className}`}
    />
  );
}

export function EmptyState({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-neutral-200 p-8 text-center">
      <p className="text-sm font-medium text-neutral-700">{title}</p>
      {children && <div className="mt-2 text-sm text-neutral-500">{children}</div>}
    </div>
  );
}

export function PlannedNote({ children }: { children: ReactNode }) {
  return (
    <div className="ux4g-alert ux4g-alert-info rounded-xl border border-gov-200" role="note">
      <span className="ux4g-alert-icon" aria-hidden="true">
        <Info className="h-5 w-5" strokeWidth={1.75} />
      </span>
      <div className="ux4g-alert-content">
        <p className="ux4g-alert-title text-xs font-semibold uppercase tracking-wide">
          Planned
        </p>
        <p className="ux4g-alert-message text-sm">{children}</p>
      </div>
    </div>
  );
}

/** UX4G progress bar (track/fill pattern) themed with the gov primary ramp. */
export function ProgressBar({
  value,
  label,
}: {
  value: number; // 0–100
  label: string;
}) {
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className="ux4g-progress-bar-track w-32 rounded-full"
      style={
        {
          "--ux4g-progress-value": value,
          "--ux4g-progress-track": "#f5f5f5",
          "--ux4g-progress-fill-start": "#4a2bc2",
          "--ux4g-progress-fill-end": "#6a4eff",
        } as React.CSSProperties
      }
    >
      <div className="ux4g-progress-bar-fill rounded-full" />
    </div>
  );
}
