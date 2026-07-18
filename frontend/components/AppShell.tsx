"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import {
  Building2,
  Database,
  LayoutDashboard,
  LineChart,
  Map as MapIcon,
  Megaphone,
  Menu,
  ScanSearch,
  Siren,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import Aurora from "@/components/fx/Aurora";
import ApiOfflineBanner from "@/components/ApiOfflineBanner";
import BackendStatus from "@/components/BackendStatus";

const NAV = [
  { href: "/", label: "Overview", Icon: LayoutDashboard },
  { href: "/map", label: "Live Map", Icon: MapIcon },
  { href: "/forecast", label: "Forecast", Icon: LineChart },
  { href: "/attribution", label: "Source Attribution", Icon: ScanSearch },
  { href: "/enforcement", label: "Enforcement", Icon: Siren },
  { href: "/advisory", label: "Citizen Advisory", Icon: Megaphone },
  { href: "/cities", label: "Cities", Icon: Building2 },
  { href: "/data", label: "Data & Pipeline", Icon: Database },
];

function Nav() {
  const pathname = usePathname();
  const reduce = useReducedMotion();
  return (
    <nav aria-label="Primary" className="flex flex-col gap-1 p-3">
      {NAV.map(({ href, label, Icon }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-gov-500 ${
              active
                ? "font-medium text-gov-700"
                : "text-neutral-600 hover:bg-neutral-100 hover:text-neutral-800"
            }`}
          >
            {active && (
              <motion.span
                layoutId="nav-pill"
                aria-hidden="true"
                className="absolute inset-0 rounded-lg border border-gov-200 bg-gov-50"
                transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 400, damping: 32 }}
              />
            )}
            <Icon aria-hidden="true" className="relative h-4 w-4 shrink-0" strokeWidth={1.75} />
            <span className="relative">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close the mobile drawer on navigation.
  useEffect(() => setOpen(false), [pathname]);

  return (
    <div className="flex min-h-screen">
      <Aurora />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-gov-600 focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to main content
      </a>

      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-neutral-200 bg-white/85 backdrop-blur lg:flex">
        <Brand />
        <Nav />
        <div className="mt-auto p-3">
          <BackendStatus />
        </div>
      </aside>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/60"
            onClick={() => setOpen(false)}
          />
          <motion.aside
            initial={{ x: -40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="absolute left-0 top-0 flex h-full w-64 flex-col border-r border-neutral-200 bg-white"
          >
            <Brand />
            <Nav />
            <div className="mt-auto p-3">
              <BackendStatus />
            </div>
          </motion.aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Government identity strip (prototype for a GoI smart-city deployment) */}
        <div className="flex items-center justify-between gap-3 bg-gov-900 px-4 py-1.5 text-[11px] text-gov-100 sm:px-6">
          <span lang="hi">
            भारत सरकार <span aria-hidden="true">|</span>{" "}
            <span lang="en">Government of India — prototype</span>
          </span>
          <span className="hidden sm:inline text-gov-200">
            Built on UX4G · Digital India design system
          </span>
        </div>

        <ApiOfflineBanner />

        {/* Mobile top bar */}
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-neutral-200 bg-white/90 px-4 py-3 backdrop-blur lg:hidden">
          <button
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
            className="rounded-md border border-neutral-300 px-2.5 py-1.5 text-sm text-neutral-700 outline-none focus-visible:ring-2 focus-visible:ring-gov-500"
          >
            <Menu aria-hidden="true" className="h-4 w-4" />
          </button>
          <span className="font-semibold tracking-tight">
            UrbanAir <span className="gradient-text">Intel</span>
          </span>
        </header>

        <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
          {children}
        </main>

        <footer className="border-t border-neutral-200 px-6 py-4 text-xs text-neutral-400">
          UrbanAir Intel — CAAQMS · Sentinel-5P · NASA FIRMS · OSM · 1 km grid digital twin.
          Data is indicative; verify with official CPCB bulletins before enforcement action.
        </footer>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 border-b border-neutral-200 px-4 py-4">
      <span
        aria-hidden="true"
        className="relative grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-gov-700 to-gov-500 text-sm font-bold text-white shadow-lg shadow-gov-500/30"
      >
        UA
      </span>
      <div className="leading-tight">
        <p className="font-semibold tracking-tight">
          UrbanAir <span className="gradient-text">Intel</span>
        </p>
        <p className="text-[11px] text-neutral-500">Delhi NCR · 1 km grid</p>
      </div>
    </div>
  );
}
