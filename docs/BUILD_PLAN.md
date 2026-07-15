# Build Plan — Urban Air Quality Intelligence Platform

Source: hackathon problem statement ("AI-Powered Urban Air Quality Intelligence
for Smart City Intervention") + accompanying deep research report
(architecture blueprint, GitHub repos, knowledge.md spec, literature review).

Target scope for the prototype: **Delhi NCR** as the primary demo city (worst
data availability problem, highest judge familiarity), architected so a
second city (Mumbai or Bengaluru) can be added by changing a bounding box.

---

## Step 1 — Project Setup & Architecture Foundation *(this step — implemented)*
Repo scaffold, Docker Compose (Postgres/PostGIS + Redis), FastAPI backend
skeleton, Next.js 14 + TS frontend skeleton, env config, folder-per-module
layout matching the pipeline stages below.

## Step 2 — Data Ingestion Layer *(implemented)*
Async ingestion services for the four modalities in the research report's
Table 2: CAAQMS via OpenAQ SDK (hourly), NASA FIRMS thermal anomalies
(3-hourly), OSM Overpass land-use/road vectors (monthly static pull),
Sentinel-5P NO2/SO2 (daily, NRTI+OFFL). Land in Postgres as raw tables.
Gap-fill sensor dropouts under 3 hours via linear interpolation.

Sentinel-5P is metadata-only in this step (product id, sensing window,
NRTI/OFFL) — the actual NetCDF download + HARP regridding onto the 1km
grid happens in Step 3/4, once the grid it projects onto exists.

Manual trigger routes (`POST /ingestion/{source}/run`) sit alongside the
APScheduler jobs so a puller can be run on demand for the demo without
waiting for its natural cadence.

## Step 3 — Geospatial Grid Engine (Digital Twin Core)
Define the 1km × 1km PostGIS grid over the target city bounding box
(EPSG:32643 for North India). Inverse Distance Weighting (IDW) to project
irregular CAAQMS point readings onto grid centroids each hour. This is the
spatial backbone every later step reads/writes against.

## Step 4 — Feature Engineering & Multi-Modal Fusion
Assemble the per-timestep data cube (grid_h × grid_w × channels): IDW'd
PM2.5/PM10, regridded S5P NO2, FIRMS fire-radiative-power proxy, OSM road
density %, OSM industrial land-use %, meteorology (wind speed/direction,
temp, humidity). Output training-ready tensors + a feature store table.

## Step 5 — Hyperlocal Predictive Forecasting Model
Train a ConvLSTM (video-frame-style spatial forecasting, per the
PM2.5-GNN / ForecastPro reference repos) for 24–72hr AQI forecasts at grid
resolution. Fall back to a gradient-boosted per-grid-cell baseline if time
is short. Evaluate with RMSE against a persistence baseline (matches the
PS brief's evaluation focus). Serve via a FastAPI inference endpoint.

## Step 6 — Multi-Agent Intelligence Layer
LangGraph agent graph: **Monitoring Agent** (watches forecast tensor for
WHO-threshold breaches) → **Source Attribution Agent** (cross-references
FIRMS upwind fires, OSM industrial zones, NO2 anomalies, traffic timing to
score likely pollution source) → **Enforcement Prioritization Agent**
(ranks grid cells by AQI × residential density, drafts an inspector patrol
route). LLM-backed reasoning with structured JSON outputs between agents.

## Step 7 — City & Citizen Dashboard (Frontend)
Next.js map dashboard: live + forecast AQI heatmap over the grid, source
hotspot markers with attribution confidence, enforcement recommendation
panel, ward-level health-risk advisory cards, and LLM-generated citizen
alert copy in regional languages (Hindi for Delhi, extensible per city).

## Step 8 — Integration, Deployment & Demo Packaging
Wire frontend ↔ backend end-to-end, deploy (Render for API/Postgres,
Vercel for frontend), produce the architecture diagram, presentation deck,
and demo video called for in the PS brief's "Expected Deliverables," and
map results back to the judging criteria (Innovation, Business Impact,
Technical Excellence, Scalability, UX).

---

### Notes on scope discipline
Steps 2–6 are individually demo-able in isolation — each should leave a
working, testable slice (e.g., step 2 done = you can query raw ingested
rows in Postgres; step 5 done = you can hit `/forecast/{grid_id}` and get
numbers back). This means the project is presentable at any checkpoint,
not just at the very end.
