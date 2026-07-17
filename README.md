# UrbanAir Intel

AI-powered Urban Air Quality Intelligence platform — fuses CAAQMS ground
sensors, Sentinel-5P satellite imagery, NASA FIRMS fire data, OSM land-use
layers, and meteorological forecasts to move city administrators from
reactive AQI monitoring to proactive, source-attributed intervention.

Built for the **"AI-Powered Urban Air Quality Intelligence for Smart City
Intervention"** hackathon problem statement. Full build plan:
[`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md).

## Status

**Steps 1–7 built and live-verified**; Step 8 (deployment + demo packaging) in
progress. Pipeline demo path:

```bash
curl -X POST "http://localhost:8000/ingestion/caaqms/run"     # live sensor pull
curl -X POST "http://localhost:8000/grid/generate"            # 1km grid (once)
curl -X POST "http://localhost:8000/grid/materialize"         # IDW onto grid
curl "http://localhost:8000/grid/readings?parameter=pm25"     # gridded state
curl "http://localhost:8000/forecast/grid?horizon_hours=24"   # ConvLSTM rollout
curl -X POST "http://localhost:8000/agents/run?synthetic_grid_id=1401"  # drill
curl "http://localhost:8000/advisory?lang=hi"                 # Hindi advisory
```

Tests (all external HTTP mocked): `cd backend && pytest tests/ -v` — 38 green.
Rendered architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
demo script + deck outline: [`docs/DEMO.md`](docs/DEMO.md).

## Architecture (target end state)

```
                    ┌─────────────────────────────────────────┐
                    │              Data Sources                │
                    │  CAAQMS (OpenAQ) · Sentinel-5P · FIRMS   │
                    │  OSM Overpass · Meteorological forecast  │
                    └───────────────────┬───────────────────────┘
                                        │
                                 ┌──────▼──────┐
                                 │  Ingestion   │  (Step 2)
                                 └──────┬──────┘
                                        │
                          ┌─────────────▼─────────────┐
                          │  Geospatial Grid Engine     │  (Step 3)
                          │  1km × 1km PostGIS grid,     │
                          │  IDW interpolation           │
                          └─────────────┬─────────────┘
                                        │
                          ┌─────────────▼─────────────┐
                          │  Feature Fusion / Data Cube │  (Step 4)
                          └─────────────┬─────────────┘
                                        │
                     ┌──────────────────┼──────────────────┐
                     │                                     │
            ┌────────▼────────┐                  ┌─────────▼─────────┐
            │ Forecasting Model │                  │  Multi-Agent Layer │
            │ (ConvLSTM, Step 5)│                  │  (LangGraph, Step 6)│
            └────────┬────────┘                  └─────────┬─────────┘
                     │                                     │
                     └──────────────────┬──────────────────┘
                                        │
                                ┌───────▼───────┐
                                │  FastAPI Backend │
                                └───────┬───────┘
                                        │
                                ┌───────▼───────┐
                                │ Next.js Dashboard │  (Step 7)
                                └───────────────┘
```

## Tech stack

| Layer | Choice |
|---|---|
| Backend / agents | Python, FastAPI, LangGraph, PyTorch |
| Geospatial store | PostgreSQL + PostGIS |
| Cache / task queue backing | Redis |
| Forecasting model | ConvLSTM (ST-GNN literature-informed) |
| LLM | Pluggable — Groq or Anthropic API via `.env` |
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind |
| Map rendering | Leaflet / Mapbox GL (wired in Step 7) |
| Local infra | Docker Compose |

## Repo layout

```
urbanair-intel/
├── backend/                # FastAPI service
│   ├── app/
│   │   ├── core/             # settings, db session
│   │   ├── api/routes/       # HTTP route modules
│   │   ├── ingestion/        # Step 2 — CAAQMS/FIRMS/OSM/S5P pullers + scheduler
│   │   ├── geospatial/       # Step 3 — grid + IDW engine
│   │   ├── models/           # Step 5 — forecasting model + inference
│   │   ├── agents/           # Step 6 — LangGraph agent graph
│   │   └── schemas/          # Pydantic request/response models
│   └── tests/                # pytest — mocks all external HTTP, no live keys needed
├── frontend/                # Next.js 14 dashboard
├── infra/postgres/          # DB init scripts (PostGIS extension)
└── docs/                    # Build plan, architecture notes
```

## Getting started (local dev)

**Prerequisites:** Docker + Docker Compose, Node 20+, Python 3.11+.

```bash
# 1. Copy env template and fill in API keys as you reach steps that need them
cp .env.example .env

# 2. Start Postgres + PostGIS and Redis
docker compose up -d

# 3. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# → http://localhost:8000/health

# 4. Frontend (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

## Roadmap

See [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md) for the full 8-step plan.
Each step is designed to leave a demo-able slice of the product working.
