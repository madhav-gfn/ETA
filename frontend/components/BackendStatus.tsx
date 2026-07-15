"use client";

import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "@/lib/api";

export default function BackendStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setError("Backend not reachable — is `uvicorn` running on :8000?"));
  }, []);

  if (error) {
    return <p className="text-sm text-red-400">{error}</p>;
  }

  if (!health) {
    return <p className="text-sm text-slate-500">Checking backend connection…</p>;
  }

  return (
    <p className="text-sm text-emerald-400">
      Backend reachable — {health.service} ({health.environment})
    </p>
  );
}
