# Build Plan — Urban Air Quality Intelligence Platform

Source: hackathon problem statement ("AI-Powered Urban Air Quality Intelligence
for Smart City Intervention") + accompanying deep research report
(architecture blueprint, GitHub repos, knowledge.md spec, literature review).

Target scope for the prototype: **Delhi NCR** as the primary demo city (worst
data availability problem, highest judge familiarity), architected so a
second city (Mumbai is already registered) can be added by changing a
bounding box — no code changes needed elsewhere.

Judging criteria this plan is built against (PS brief): **Business Impact
25%, Technical Excellence 25%, Scalability 20%, Innovation 15%, User
Experience 15%.**

## Status snapshot

| Step | Name | Status |
|---|---|---|
| 1 | Project setup & architecture foundation | ✅ Done |
| 2 | Data ingestion layer | ✅ Done — live-verified (OpenAQ v3 endpoints fixed; Overpass mirrors+tiling; FIRMS buffered bbox; + Open-Meteo puller added) |
| 3 | Geospatial grid engine | ✅ Done — 2,805 cells, hourly IDW with LOO-RMSE |
| 4 | Feature engineering & multi-modal fusion | ✅ Done — 11-channel cubes (S5P raster regrid = documented NaN-flagged slot) |
| 5 | Hyperlocal predictive forecasting model | ✅ Done — production-hardened pipeline (masked loss, leakage-free purged splits, checkpoint-stat serving); **1h RMSE 17.4 vs persistence 18.8 — beats baseline by 7.3%** on 312 held-out windows. 24h-direct: 34.1 vs 31.7 — does *not* beat the honest same-hour-yesterday baseline (the earlier "24h win" was an evaluation artifact: the old persistence baseline was inflated by mean-filling unobserved cells). Documented next steps: time-of-day channels, 24h input window, residual-vs-persistence target |
| 6 | Multi-agent intelligence layer | ✅ Done — LangGraph + Groq, verified live via synthetic drill |
| 7 | City & citizen dashboard | ✅ Done — Leaflet heatmap, forecast slider, enforcement panel, en/hi advisory |
| 8 | Integration, deployment & demo packaging | 🔨 In progress — ARCHITECTURE.md + DEMO.md written; deployment pending |

---

## Step 1 — Project Setup & Architecture Foundation ✅ Done

**Goal:** a running, testable skeleton before any domain logic is written.

**What's implemented:**
- Repo scaffold: `backend/` (FastAPI) and `frontend/` (Next.js 14 + TypeScript
  + Tailwind), with documented-but-empty module folders for every future step
  (`ingestion/`, `geospatial/`, `models/`, `agents/`) so the architecture is
  visible before code lands there.
- `docker-compose.yml`: Postgres+PostGIS and Redis, with a PostGIS-enabling
  init script (`infra/postgres/init.sql`).
- FastAPI app with CORS, a `/health` route, and a `lifespan` hook that now
  also drives Step 2's DB init + scheduler.
- Next.js skeleton with a status page that pings the backend health check
  and shows build-plan progress.
- `requirements.txt` pre-populated with every dependency later steps need;
  `.env.example` covering every future API key.
- Verified: backend boots and both routes respond; frontend builds clean
  (`npm run build`) with a patched Next.js version (14.2.35 — the
  unpatched 14.2.18 had a disclosed RSC vulnerability, caught during setup).

**Acceptance criteria (met):** `docker compose up -d`, `uvicorn` serves
`/health` with 200, `npm run dev` renders the status page and shows
"Backend reachable."

---

## Step 2 — Data Ingestion Layer ✅ Done

**Goal:** get all four raw data modalities from the research report's Table 2
landing in Postgres, on their own real-world cadences, without needing Step
3's grid to exist yet.

**What's implemented — four pullers, matched to each source's actual API:**

| Puller | Source | Cadence | Notes |
|---|---|---|---|
| `caaqms_openaq.py` | OpenAQ v3 SDK (proxy for CAAQMS) | Hourly | pm25/pm10/no2/so2/co/o3; gap-fills sensor dropouts <3h via linear interpolation (Section 1.1) |
| `firms_fires.py` | NASA FIRMS `/api/area/csv` | Every 3h | VIIRS_SNPP_NRT + MODIS_NRT; confidence, FRP (megawatts), day/night flag |
| `osm_landuse.py` | Overpass API (no key) | Monthly | `landuse=industrial\|residential`, `highway=primary\|trunk`, static batch |
| `sentinel5p.py` | Copernicus CDSE OData catalog | Daily | L2\_\_NO2\_\_\_ / L2\_\_SO2\_\_\_ product **metadata** (id, sensing window, NRTI/OFFL) — raster download + regridding deferred to Step 3/4 |

**Data model:** `caaqms_readings`, `fire_detections`, `osm_land_use_features`,
`sentinel5p_products`, `ingestion_run_log` — plain lat/lon columns, no
PostGIS geometry yet (that arrives with the grid in Step 3, not before it's
needed).

**API surface:** `POST /ingestion/{caaqms|firms|osm|sentinel5p}/run` (manual
trigger, demo-friendly), `GET /ingestion/status` (run history), `GET
/ingestion/caaqms/latest`.

**Scheduling:** APScheduler in-process, one job per cadence above, started
in the FastAPI `lifespan` hook (skipped when `ENVIRONMENT=test`).

**Testing:** 29 pytest tests — gap-fill math, CSV/JSON parsing per source,
OData filter string construction, and route wiring (pullers mocked at the
boundary, since this dev sandbox can't reach OpenAQ/FIRMS/Overpass/CDSE
directly). **Not yet verified against live APIs with real keys** — that's a
prerequisite before Step 2 can be called demo-ready, not just code-complete.

**Acceptance criteria (met for code; live-data check still open):**
`pytest tests/ -v` → 29/29 green. Open: run each `/ingestion/*/run` route
with real `OPENAQ_API_KEY` / `NASA_FIRMS_MAP_KEY` / CDSE credentials and
confirm rows land in each table.

---

## Step 3 — Geospatial Grid Engine (Digital Twin Core) 📋 Planned

**Goal:** give every later step one shared spatial index — the 1km×1km grid
— so ingestion output, features, forecasts, and agent output can all be
addressed by the same `grid_id`.

**Design:**
1. **Grid generation.** Project the city bbox from Step 2's `cities.py` into
   `EPSG:32643` (UTM 43N), tile it into 1km×1km cells, store each cell as a
   PostGIS `POLYGON` with a stable integer `grid_id` and its centroid. One-time
   generation per city, re-run only if a city's bbox changes.
   - New table: `grid_cells(grid_id, city_slug, geom POLYGON, centroid_lat,
     centroid_lon, row_idx, col_idx)` — `row_idx`/`col_idx` give the
     ConvLSTM (Step 5) its 2D array layout for free.
2. **IDW interpolation.** Project irregular CAAQMS sensor readings (Step 2's
   `caaqms_readings`) onto grid centroids every hour:

   ```
   Ẑ(x₀) = Σᵢ wᵢ·Zᵢ  /  Σᵢ wᵢ,      wᵢ = 1 / d(x₀, xᵢ)^p
   ```

   `p = 2` by default (research report's stated typical value); only sensors
   within a configurable search radius (e.g. 15km) contribute, so a grid cell
   far from any station doesn't get a falsely confident estimate.
   - New table: `grid_readings(grid_id, parameter, value, measured_at,
     interpolation_method, contributing_sensor_count)`.
3. **Kriging (stretch).** Ordinary Kriging as a variance-aware alternative to
   IDW where the literature review flags it (Section 3.1) — only if IDW's
   RMSE against held-out stations isn't good enough; not required for MVP.
4. **Materialization job.** An hourly job (APScheduler, same pattern as Step
   2) that: pulls the latest hour of `caaqms_readings`, runs IDW per
   parameter, writes `grid_readings`. This is the first job that *depends on*
   Step 2's output rather than pulling from an external API.

**API surface:** `GET /grid/cells?city_slug=` (cell geometries for the map),
`GET /grid/readings?city_slug=&parameter=&at=` (latest or historical
gridded state).

**Acceptance criteria:** grid generation is deterministic and idempotent
(re-running doesn't duplicate cells); IDW output validated by leave-one-out
cross-validation against real station readings (hold out one CAAQMS station,
interpolate its value from the rest, compare); `/grid/readings` returns a
full grid snapshot in well under a second for the Delhi NCR bbox.

---

## Step 4 — Feature Engineering & Multi-Modal Fusion 📋 Planned

**Goal:** assemble the per-timestep data cube the forecasting model actually
trains on — this is where every Step 2 modality plus Step 3's grid come
together.

**One addition to ingestion not in the original Table 2:** a lightweight
**meteorology puller** (wind speed/direction, temperature, humidity) is
needed here — the research report's feature cube and Gaussian-plume math
both require it, but it wasn't one of the four "pollution-specific" sources
in Table 2. Plan: **Open-Meteo** (free, no API key, generous rate limits) for
forecast + historical wind/temp/humidity by lat/lon, pulled hourly per grid
centroid or per city and reused across cells.

**Fusion pipeline (per the research report's Section 2, "Feature Engineering
& Multi-Modal Fusion"):**
1. **Point-source interpolation** — already done in Step 3 (IDW).
2. **Raster regridding (satellite)** — download the actual Sentinel-5P NetCDF
   for products Step 2 catalogued, apply a QA-value filter (discard pixels
   with QA < 0.75), regrid orbital swaths onto the 1km grid. HARP's
   `bin_spatial` is the reference approach; if HARP proves too heavy to wire
   up in hackathon time, RBF regridding via `scipy.interpolate` is the
   documented fallback (both are in the research report's reference repos).
3. **Vector rasterization (OSM)** — for each grid cell, compute continuous
   proxy features from Step 2's `osm_land_use_features`: road density
   (km of primary/trunk road per km²) and % industrial land-use area.
4. **Meteorology join** — attach wind speed/direction, temperature, humidity
   per grid cell per hour from the new Open-Meteo puller.
5. **Data cube assembly** — stack channel-wise into a tensor
   `(H, W, C)` per timestep, where `C` = {interpolated PM2.5, interpolated
   PM10, regridded NO2, FIRMS FRP-proxy, road density, industrial land-use %,
   wind speed, wind direction, temperature, humidity}.

**Storage:** a `feature_cube_manifest` table (city_slug, timestep, channel
list, storage path) pointing at cube files on disk/object storage (`.npy` or
Parquet) — the tensors themselves are too large/columnar for Postgres rows.

**API surface:** `GET /features/cube?city_slug=&at=` returns the manifest +
a signed path/URL to fetch the tensor; mainly consumed by Step 5's training
job, not the frontend.

**Acceptance criteria:** one full day of Delhi NCR data assembles into a
complete, channel-labeled cube with no silent NaNs (missing satellite
coverage is explicitly flagged, not zero-filled); a notebook/script can load
one cube and visualize each channel as a heatmap for a sanity check.

---

## Step 5 — Hyperlocal Predictive Forecasting Model 📋 Planned

**Goal:** 24–72hr AQI forecasts at 1km grid resolution, evaluated against a
persistence baseline (the PS brief's explicit evaluation focus).

**Model:** ConvLSTM, following the PM2.5-GNN / ForecastPro reference repos —
feature cubes are treated as video frames; convolutional layers capture
spatial structure per timestep, LSTM gating captures temporal evolution.
Input: a sliding window of the last *N* hourly cubes from Step 4. Output:
predicted PM2.5 (and optionally PM10/NO2) grid for each of the next 24/48/72
hours.

**Baseline (fallback if training time is tight):** per-grid-cell gradient
boosted regression (scikit-learn) using lag features + meteorology — no
spatial convolution, but fast to train and a legitimate reference point.

**Training pipeline:**
- Chronological train/val/test split (no random shuffling — this is a time
  series; shuffling would leak future information into training).
- Loss: MSE on the predicted grid, evaluated as RMSE for reporting.
- Walk-forward validation: train on week 1, validate on week 2, roll forward.

**Evaluation metric** (research report Section 3.3):

```
RMSE = sqrt( (1/N) · Σ (ŷᵢ - yᵢ)² )
```

reported against a **persistence baseline** (tomorrow's AQI = today's AQI at
the same grid cell) — the PS brief's literal evaluation focus, so this
comparison is a required output, not just a nice-to-have.

**Serving:** trained checkpoint loaded once at API startup; `models/`
gets `convlstm.py` (architecture), `inference.py` (loads checkpoint, serves
predictions), `evaluate.py` (RMSE-vs-persistence harness), `baseline.py`
(GBM fallback).

**API surface:** `GET /forecast/{grid_id}?horizon_hours=24|48|72`, `GET
/forecast/grid?city_slug=&horizon_hours=` (full-grid forecast for the map).

**Acceptance criteria:** model RMSE beats the persistence baseline at all
three horizons on held-out data; inference for a full-city grid completes
fast enough for interactive dashboard use (target: under 2 seconds).

---

## Step 6 — Multi-Agent Intelligence Layer 📋 Planned

**Goal:** turn Step 5's forecasts into prescriptive, evidence-backed
enforcement action — the PS brief's "Enforcement Intelligence &
Prioritisation Agent" — using the LangGraph pattern in the research report's
Section 4.

**Agent graph:**
1. **Monitoring Agent** — watches Step 5's forecast tensor; if any grid cell
   crosses a WHO-threshold anomaly (configurable, e.g. PM2.5 > 150 µg/m³),
   emits an `AnomalyAlert{grid_id, parameter, forecast_value, timestamp}`.
2. **Source Attribution Agent** — system prompt per the research report:
   *"You are an Environmental Forensics Expert. Analyze the provided anomaly
   payload. Query the FIRMS database for fire anomalies within a 50km
   upwind radius based on current wind vectors. Query OSM for high-density
   industrial zones in the target grid. Output a probability score for the
   anomaly source."* Decision logic: high upwind FRP → biomass burning;
   disproportionate NO2 in an industrial-tagged grid → industrial emissions;
   anomaly aligned with dense highway tags at peak commute hours → vehicular.
   Tools: reads Step 2's `fire_detections` and `osm_land_use_features`
   directly (no new external calls needed — attribution runs on data already
   ingested).
3. **Enforcement Prioritization Agent** — system prompt: *"You are a
   Municipal Dispatch Coordinator. Based on high-confidence attributions,
   generate a patrol route for municipal inspectors."* Ranks grid cells by
   `AQI magnitude × residential density`, then calls an OSM routing engine
   (OSRM, self-hostable, no key) to produce a shortest-path inspector
   itinerary across the top-ranked cells.

**State schema:** typed dicts/Pydantic models for `AnomalyAlert`,
`AttributionResult` (source category + confidence score + supporting
evidence), `EnforcementPlan` (ranked grid cells + patrol route + rationale)
— each a JSON-serializable handoff between graph nodes, so the frontend can
render the same objects the agents reasoned over.

**LLM provider:** pluggable per `.env`'s `LLM_PROVIDER` (Groq default for
speed/cost, Anthropic as an alternative) — abstracted behind one thin
wrapper so swapping providers doesn't touch agent logic.

**API surface:** `POST /agents/run?grid_id=` (manual trigger for a specific
anomaly, demo-friendly), `GET /agents/recommendations?city_slug=` (latest
enforcement plans for the dashboard).

**Acceptance criteria:** given a synthetic anomaly (useful since real
anomalies may not occur during a demo window), the graph runs end-to-end and
produces a plausible attribution + patrol route with a documented rationale
a domain expert could sanity-check (matches the PS brief's evaluation focus
on "enforcement recommendation quality rated by domain experts").

---

## Step 7 — City & Citizen Dashboard 📋 Planned

**Goal:** the PS brief's "Citizen Health Risk Advisory System" plus a
city-administrator view, in one Next.js app.

**Pages/components:**
- **Map view** (Leaflet or Mapbox GL — token already scaffolded in Step 1's
  `.env.example`): AQI heatmap over the grid (live + forecast, with a
  timeline slider for the 24/48/72hr horizons from Step 5), fire/hotspot
  markers from Step 2/6, enforcement patrol routes from Step 6.
- **Enforcement panel** — Step 6's ranked recommendations with the
  attribution rationale, so an administrator can see *why* a grid cell was
  flagged, not just that it was.
- **Health advisory cards** — ward-level risk framed against vulnerable-
  population proxies (hospitals/schools from OSM tags already in Step 2's
  data, extended with a couple more Overpass tag queries); LLM-generated
  plain-language advisory copy.
- **Language toggle** — citizen alert copy generated in Hindi for Delhi (the
  PS brief's example: Kannada for Bengaluru, Tamil for Chennai) — an i18n
  layer over the LLM-generated advisory text, not a full UI translation.

**Data flow:** all panels read from the FastAPI routes built in Steps 3, 5,
and 6 — no new backend endpoints needed here, just consuming them (the
`lib/api.ts` client from Step 1 grows one function per endpoint).

**Acceptance criteria:** a single page loads live grid state, a forecast for
a selected horizon, and current enforcement recommendations without a
full-page reload; map interactions (click a grid cell) surface that cell's
forecast + attribution in a side panel.

---

## Step 8 — Integration, Deployment & Demo Packaging 📋 Planned

**Goal:** the PS brief's explicit deliverables — working prototype,
architecture diagram, presentation deck, demo video — plus a defensible
story against the judging weights.

**Deployment:** backend + Postgres/PostGIS + Redis to Render (Docker
Compose translates directly to Render's service model); frontend to Vercel;
environment variables set from `.env.example`'s real-key equivalents.

**Architecture diagram:** formalize the ASCII diagram in the root `README.md`
into a proper diagram (source kept in `docs/`), annotated with which repo
folder implements which box, so it doubles as an onboarding aid.

**Presentation deck outline**, mapped to the judging weights so nothing is
under-argued relative to its scoring weight:
- Business Impact (25%) — the problem-context numbers already in the PS
  brief (1.67M premature deaths/year, 24 of top-50 polluted cities are
  Tier 1/2, only 31% of CAQMS-covered cities have actionable response
  protocols) framed against what this platform closes.
- Technical Excellence (25%) — architecture diagram + the RMSE-vs-persistence
  result from Step 5 + the attribution/enforcement rationale from Step 6.
- Scalability (20%) — the multi-city bbox pattern already built in Step 2's
  `cities.py` (Mumbai is a one-line addition, not a redesign).
- Innovation (15%) — the fused source-attribution + prescriptive enforcement
  loop (most AQI dashboards stop at monitoring; this doesn't).
- User Experience (15%) — the Step 7 dashboard walkthrough.

**Demo video:** a scripted walkthrough — live grid → forecast horizon slider
→ an anomaly → attribution rationale → enforcement patrol route → citizen
advisory in Hindi — following the actual data flow through the pipeline
rather than a feature-by-feature tour.

**Acceptance criteria:** a judge can go from the deployed URL to
understanding the full pipeline in under 5 minutes without narration, and
every judging-criteria bullet above has a corresponding concrete artifact
(not just a claim) in the deck.

---

### Notes on scope discipline
Steps 2–6 are individually demo-able in isolation — each has left (or will
leave) a working, testable slice rather than only becoming useful once every
step is done. This means the project is presentable at any checkpoint, which
matters given hackathon time pressure: if Step 6 turns out to be too
ambitious to finish, Steps 1–5 alone already tell a coherent story (raw data
→ gridded digital twin → fused features → forecasts beating a real
baseline).