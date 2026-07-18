# UrbanAir Intel — Frontend Sitemap & Backend Contract

Maps every frontend route to the backend endpoints it consumes today and the
endpoints it will need as the backend matures. Use this as the checklist when
improving the backend: anything marked **NEEDED** is a UI surface already built
(or stubbed with a "Planned" note) waiting for data.

All routes live under `frontend/app/` (Next.js 14 App Router). Global shell:
`components/AppShell.tsx` — sidebar nav, mobile drawer, skip-to-content link,
API health indicator (polls `GET /health` every 30 s).

---

## Route map

```
/                     Overview (city KPIs, advisory, latest intervention)
├── /map              Live AQI map + forecast timeline scrubber
├── /forecast         Forecast explorer + model-vs-persistence metrics
├── /attribution      Source attribution runs with evidence & confidence
├── /enforcement      Agent pipeline: drill trigger, patrol routes, run history
├── /advisory         Citizen advisory in regional languages + health bands
├── /cities           Multi-city comparison (Delhi NCR live, 4 planned)
└── /data             Data sources, pipeline status, grid stats
```

---

## Per-page contract

### `/` — Overview (`app/page.tsx`)
**Uses today:**
- `GET /grid/readings?city_slug&parameter=pm25` — mean/peak PM2.5 computed client-side
- `GET /forecast/metrics?city_slug` — RMSE badge
- `GET /agents/recommendations?city_slug` — latest intervention card
- `GET /advisory?city_slug&lang` (via `AdvisoryCard`)

**NEEDED:**
- `GET /stats/summary?city_slug` — server-computed mean/max/category + 24h trend
  delta (client currently averages the full readings payload; wasteful at scale)
- WebSocket or SSE push for live snapshot updates (currently load-time fetch only)

### `/map` — Live Map (`app/map/page.tsx`, `components/AqiMap.tsx`)
**Uses today:**
- `GET /grid/cells?city_slug`
- `GET /grid/readings?city_slug&parameter`
- `GET /forecast/grid?city_slug&horizon_hours=72` — horizon scrubber (Live/+1h…+72h)
- `GET /agents/recommendations` — anomaly marker + patrol route overlay

**NEEDED:**
- Vector/GeoJSON tiles or cell simplification for city counts >5k cells (payload size)
- Parameter switcher backend support beyond pm25 (pm10, no2 exist in ingestion —
  expose via `/grid/readings?parameter=`; UI toggle is trivial to add once verified)
- Station locations endpoint (`GET /stations?city_slug`) to render CAAQMS markers
- Ward boundary GeoJSON (`GET /wards?city_slug`) for ward-level choropleth mode

### `/forecast` — Forecast Explorer (`app/forecast/page.tsx`)
**Uses today:**
- `GET /forecast/grid?horizon_hours=72` — per-horizon city mean/peak table
- `GET /forecast/metrics` — 24h-direct + 1h RMSE vs persistence

**NEEDED:**
- `GET /forecast/cell/{grid_id}` — per-cell time series for trend charts
- Uncertainty quantification in forecast response (p10/p90 bands)
- Scenario endpoints (wind shift / rain washout what-ifs) — stretch

### `/attribution` — Source Attribution (`app/attribution/page.tsx`)
**Uses today:**
- `GET /agents/recommendations` — reads `attribution` (category, confidence,
  rationale, evidence list, llm_used) from each run

**NEEDED:**
- `GET /attribution/wards?city_slug` — standing ward-level attribution heatmap
  (today attribution only exists inside anomaly-triggered agent runs)
- Emission-inventory comparison endpoint (judged criterion: accuracy vs
  ground-truth inventories)
- Construction permits / industrial registry ingestion + overlay data

### `/enforcement` — Enforcement Intelligence (`app/enforcement/page.tsx`)
**Uses today:**
- `POST /agents/run?city_slug&synthetic_grid_id` — drill trigger
- `GET /agents/recommendations` — run history (client keeps session-local list)
- `GET /grid/cells` — picks the central-Delhi cell for drills

**NEEDED:**
- Persisted run history with pagination (`GET /agents/runs?limit&offset`)
- `POST /agents/runs/{id}/assign` + status transitions (dispatched → inspected →
  closed) — enables the signal-to-intervention-time metric the brief judges
- Evidence-pack export (`GET /agents/runs/{id}/report.pdf`)

### `/advisory` — Citizen Advisory (`app/advisory/page.tsx`)
**Uses today:**
- `GET /advisory?city_slug&lang` — `en` and `hi` live; kn/ta/bn/mr buttons render
  disabled and activate automatically once `lib/aqi.ts` `LANGS[].live` is flipped

**NEEDED:**
- Backend support for `lang=kn|ta|bn|mr` (LLM prompt already language-pluggable)
- `GET /advisory/wards?city_slug` — per-ward advisories vs vulnerability layer
  (schools, hospitals, outdoor-worker zones)
- Push-channel endpoints (SMS/IVR/webpush subscriptions) — stretch

### `/cities` — Multi-City (`app/cities/page.tsx`)
**Uses today:**
- `GET /grid/readings` for Delhi NCR; other four cities are static "onboarding
  planned" cards driven by `lib/aqi.ts` `CITIES[]`

**NEEDED:**
- Onboard a second city (grid definition + ingestion + training) — every backend
  table is already keyed by `city_slug`, so this is config + compute, not schema
- `GET /cities` — list of onboarded cities with headline stats (replaces the
  hardcoded `CITIES` array)
- Cross-city comparison endpoint (trend, intervention effectiveness, NCAP compliance)

### `/data` — Data & Pipeline (`app/data/page.tsx`)
**Uses today:**
- `GET /health`, `GET /grid/cells` (cell count), `GET /grid/readings` (snapshot time)
- Source table is static copy describing the five ingestion feeds

**NEEDED:**
- `GET /ingestion/status` — per-source last-run timestamp, row counts, errors
  (ingestion routes are currently POST-trigger-only with no consolidated status)
- Auth-gated manual re-ingestion buttons in the UI once that exists

---

## Shared frontend modules

| Module | Purpose |
|---|---|
| `lib/api.ts` | Typed API client — single place to add new endpoints |
| `lib/aqi.ts` | CPCB PM2.5 bands/colors/guidance, `CITIES`, `LANGS` config |
| `components/AppShell.tsx` | Nav shell (add new routes to its `NAV` array) |
| `components/ui.tsx` | Card, StatCard, Badge, Skeleton, EmptyState, PlannedNote |
| `components/AqiMap.tsx` | Leaflet map (readings/forecast/route layers) |
| `components/ForecastChart.tsx` | Recharts forecast-vs-persistence line chart (palette CVD-validated) |
| `components/fx/` | Motion/effects kit: `Aurora` (ambient bg), `Reveal` (staggered entrances), `CountUp` (animated stats) — all honor `prefers-reduced-motion` |
| `app/template.tsx` | Framer-motion route-change transition |
| `components/AqiLegend.tsx` | CPCB band legend |
| `components/AdvisoryCard.tsx` | Compact advisory widget (Overview) |
| `components/EnforcementPanel.tsx` | Alert → attribution → route panel |
| `components/BackendStatus.tsx` | Health poller in the sidebar |

## Theme — UX4G (India's government design system)

The app uses **UX4G** (NeGD/MeitY, ux4g.gov.in) via the official
`ux4g-web-components` npm package, imported in `app/layout.tsx`. Light
professional theme: UX4G indigo primary (`gov-*` in `tailwind.config.ts`,
from `--ux4g-color-primary-*` tokens), saffron secondary (`saffron-*`),
neutral grays, Noto Sans. Buttons use `.ux4g-btn` classes; the chart palette
(`#4a2bc2`/`#c47d00`) is UX4G primary/secondary, CVD-validated on white.
A Government-of-India identity strip (marked "prototype") tops every page.
UX4G components in use: `.ux4g-card` (all cards), `.ux4g-btn` primary/outline/danger
(all buttons and toggle groups), `.ux4g-alert` info/warning (PlannedNote,
ApiOfflineBanner), `.ux4g-table` (forecast + data tables), `.ux4g-breadcrumb`
(PageHeader on non-root pages), `.ux4g-progress-bar` (attribution confidence).
When adding UI, use `gov-*`/`saffron-*`/`neutral-*` — no `slate`/`sky` classes.

## Accessibility & UX conventions (keep when extending)

- Skip-to-content link; `<nav aria-label>`, `aria-current="page"` on active route
- All interactive elements keyboard-reachable with `focus-visible` rings
- Toggle groups use `role="radiogroup"`/`radio` + `aria-checked`
- Map cell selection echoed to an `aria-live="polite"` region (map itself is not
  screen-reader friendly — the tables on /forecast are the accessible equivalent)
- `prefers-reduced-motion` disables animations; color is never the only signal
  (bands always carry text labels)
- Advisory text carries `lang=` attribute for correct screen-reader pronunciation

## Adding a page checklist

1. Create `frontend/app/<route>/page.tsx` (client component, fetch via `lib/api.ts`)
2. Add the route to `NAV` in `components/AppShell.tsx`
3. Use `PageHeader` + `Card`/`StatCard` from `components/ui.tsx`
4. Mark not-yet-backed features with `PlannedNote` and record the missing
   endpoint in this file
