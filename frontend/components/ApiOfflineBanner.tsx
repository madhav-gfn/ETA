"use client";

import { TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";

/** UX4G warning alert shown app-wide whenever the backend is unreachable. */
export default function ApiOfflineBanner() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let alive = true;
    const check = () =>
      getHealth()
        .then(() => alive && setOffline(false))
        .catch(() => alive && setOffline(true));
    check();
    const id = setInterval(check, 15_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (!offline) return null;

  return (
    <div className="ux4g-alert ux4g-alert-warning border-b border-saffron-300" role="alert">
      <span className="ux4g-alert-icon" aria-hidden="true">
        <TriangleAlert className="h-5 w-5" strokeWidth={1.75} />
      </span>
      <div className="ux4g-alert-content">
        <p className="ux4g-alert-title text-sm">Backend API unreachable</p>
        <p className="ux4g-alert-message text-xs">
          Live data, forecasts and advisories cannot load. Start the API with{" "}
          <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono">
            cd backend &amp;&amp; ../evenv/python.exe -m uvicorn app.main:app --port 8000
          </code>{" "}
          — this banner clears automatically once it responds.
        </p>
      </div>
    </div>
  );
}
