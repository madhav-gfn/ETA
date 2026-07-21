# Team Setup — run UrbanAir Intel on your machine

Everything a teammate needs to go from `git clone` to a working dashboard.
Windows/macOS/Linux all work; commands below are shell-neutral unless noted.

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker Desktop | any recent | runs PostGIS + Redis |
| Python | **3.11** | torch 2.5.1 wheels target ≤3.12; 3.11 is what we pin against |
| Node.js | 18+ | frontend only |
| Git | any | |

## 2. Infrastructure

```bash
git clone <repo-url> && cd ETA
docker compose up -d          # PostGIS on host port 5433, Redis on 6379
```

**Port 5433 is deliberate** — many machines have a native PostgreSQL owning
5432 *without PostGIS*, which silently breaks grid creation. Leave it as-is.

## 3. Environment

```bash
cp .env.example .env
```

Then fill in your own keys in `.env` (never commit it; it's gitignored):

| Key | Where to get it | Needed for |
|---|---|---|
| `OPENAQ_API_KEY` | explore.openaq.org → account settings | sensor ingestion |
| `NASA_FIRMS_MAP_KEY` | firms.modaps.eosdis.nasa.gov/api/map_key | fire detections |
| `COPERNICUS_CDSE_USERNAME/PASSWORD` | dataspace.copernicus.eu signup | Sentinel-5P catalog |
| `GROQ_API_KEY` | console.groq.com | agent rationales + advisories (optional — deterministic fallbacks cover every LLM feature) |

Each teammate uses their **own** keys — the free tiers are per-account and
shared keys hit rate limits.

## 4. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Startup creates all tables automatically (`init_db`) and starts the hourly
ingestion scheduler. Verify: http://localhost:8000/health.

## 5. Data — pick one path

### Option A — restore a teammate's dump (minutes, recommended)

Someone with a populated DB runs:

```bash
docker exec urbanair-postgres pg_dump -U postgres -Fc urbanair > urbanair.dump
```

and shares three things: `urbanair.dump`, their `backend/data/cubes/` folder,
and (if not in git) `backend/checkpoints/`. You then run:

```bash
docker exec -i urbanair-postgres pg_restore -U urbanair -d urbanair --clean --if-exists < urbanair.dump
# copy cubes/ into backend/data/cubes/ , checkpoints into backend/checkpoints/
```

Cube manifest paths are stored relative to `backend/data/cubes/`, so the
restore works regardless of where your checkout lives. (Note: the dump was
created with whatever DB user the source machine used — if restore complains
about ownership, add `--no-owner`.)

### Option B — bootstrap from live APIs (~an hour, needs all keys)

```bash
cd backend
python scripts/pull_osm.py                 # OSM land use (use mirrors; see note)
curl -X POST "localhost:8000/grid/generate?city_slug=delhi-ncr"
python scripts/backfill.py                 # 90 days of sensors + meteo
python scripts/build_and_train.py delhi-ncr 30   # cubes + 1h model (hours on CPU)
```

Overpass note: `overpass-api.de` blocks some networks — the puller already
rotates through mirrors (kumi.systems etc.); just re-run if a tile 504s.

Skip the training step by taking `backend/checkpoints/*` from git or a
teammate — the API serves immediately once checkpoints exist.

## 6. Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local   # only the NEXT_PUBLIC_* lines matter here
npm run dev                     # http://localhost:3000
```

## 7. Sanity checklist

- `GET :8000/health` → ok
- `GET :8000/ingestion/status` → recent runs listed (scheduler is alive)
- `GET :8000/forecast/metrics` → RMSE numbers (checkpoints present)
- `GET :8000/forecast/grid` → 200 with grids (cubes + model in place; 409
  means cubes/checkpoint missing — see step 5)
- Dashboard at :3000 shows the colored grid

## 8. Common traps (hard-won)

- **Native Postgres on 5432 shadowing Docker** — always connect to 5433.
- Password special chars must be URL-encoded inside `DATABASE_URL` (`@` → `%40`).
- IDE import errors pointing at a system Python are bogus — select the
  project venv as interpreter.
- Long-running pulls (OSM backfill) go through `backend/scripts/`, not the
  API — uvicorn `--reload` can silently pin old workers during in-flight
  requests.
- GPU training doesn't happen here — see `docs/REMOTE_TRAINING.md` for the
  Kaggle/Colab flow (no local GPU or DB needed).
