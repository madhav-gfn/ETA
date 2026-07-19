"use client";

import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "@/lib/api";

export default function BackendStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    const check = () =>
      getHealth()
        .then((h) => alive && (setHealth(h), setError(false)))
        .catch(() => alive && setError(true));
    check();
    const id = setInterval(check, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const dot = error ? "bg-rose-500" : health ? "bg-emerald-500" : "bg-neutral-400";
  const label = error
    ? "API offline"
    : health
      ? `API online · ${health.environment}`
      : "Checking API…";

  return (
    <p
      role="status"
      className="flex items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-100 px-3 py-2 text-xs text-neutral-600"
    >
      <span aria-hidden="true" className="relative flex h-2 w-2">
        {!error && health && (
          <span className="ping-soft absolute inline-flex h-full w-full rounded-full bg-emerald-500" />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
      </span>
      {label}
    </p>
  );
}
