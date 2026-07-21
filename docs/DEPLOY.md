# Deployment: Railway + Supabase + Upstash + Vercel

$0-to-low-cost production deploy. Backend compute runs on Railway; Postgres
and Redis are external managed free tiers so Railway's usage credit only
meters the one service you actually need always-on.

```
Vercel (frontend/)  ──HTTPS──▶  Railway (backend/, Docker, port 8000)
                                        │              │
                                        ▼              ▼
                          Supabase (Postgres+PostGIS)  Upstash (Redis, TLS)
```

Backend code needs **no changes** to run against any of these — `DATABASE_URL`
and `REDIS_URL` are read from the environment (`app/core/config.py`), and the
cache layer (`app/core/cache.py`) is already fail-open, so it degrades to
"no caching" rather than erroring if Redis is briefly unreachable.

## 1. Supabase (Postgres + PostGIS)

1. Create a project at supabase.com (free tier: 500MB DB storage).
2. SQL editor → run once:
   ```sql
   create extension if not exists postgis;
   ```
   (No `postgis_topology` — see `infra/postgres/init.sql` for why the grid
   doesn't need it.)
3. Project Settings → Database → copy the **Session Pooler** connection
   string (port **5432**, not the 6543 transaction pooler — psycopg2 needs
   session-level prepared statement support that the transaction pooler
   breaks). Build `DATABASE_URL`:
   ```
   postgresql+psycopg2://postgres.<ref>:<password>@<pooler-host>:5432/postgres?sslmode=require
   ```
4. Note: free projects auto-pause after **7 days with zero DB activity**.
   Not a concern here — the ingestion scheduler (`caaqms_hourly`,
   `cube_build_hourly`, etc., all hourly) writes to the DB constantly as
   long as the Railway backend is running.

## 2. Upstash (Redis)

1. Create a free Redis database at upstash.com (free tier: 500K commands/mo,
   10GB bandwidth — comfortably covers hourly-refresh caching).
2. Copy the **TLS** connection URL (`rediss://default:<password>@<endpoint>.upstash.io:6379`).
   `redis-py`'s `from_url` auto-detects TLS from the `rediss://` scheme — no
   code change needed.

## 3. Railway (backend)

1. railway.app → sign in with GitHub → **New Project** → **GitHub Repo** →
   select this repo.
2. Service **Settings**:
   - **Root Directory** → `backend` (so Railway builds `backend/Dockerfile`
     and picks up `backend/railway.json`, which sets the healthcheck path
     and Dockerfile builder).
   - **Networking** → **Generate Domain**; set **Target Port = 8000**
     (matches the Dockerfile's `EXPOSE 8000` — no code change needed).
   - **Volumes** → new volume mounted at `/app/data`. This is where
     `build_cubes` writes the model's input `.npy` files
     (`app/features/cube.py`, `CUBE_DIR`) — without a volume they're wiped
     on every redeploy/restart and `/forecast/grid` breaks until the hourly
     job rebuilds enough history (~12h of cubes needed for serving).
3. **Variables**:
   ```
   DATABASE_URL=<Supabase session pooler string from step 1.3>
   REDIS_URL=<Upstash rediss:// URL from step 2.2>
   ENVIRONMENT=production
   BACKEND_CORS_ORIGINS=http://localhost:3000
   CACHE_ENABLED=true
   CACHE_TTL_SECONDS=7200
   OPENAQ_API_KEY=...
   NASA_FIRMS_MAP_KEY=...
   COPERNICUS_CDSE_USERNAME=...
   COPERNICUS_CDSE_PASSWORD=...
   LLM_PROVIDER=groq
   GROQ_API_KEY=...
   ANTHROPIC_API_KEY=...
   ```
   (Update `BACKEND_CORS_ORIGINS` once the Vercel domain exists — step 5.)
4. Deploy. Logs should show `Ingestion scheduler started`.

## 4. Bootstrap (once, after backend + Supabase are live)

Install the Railway CLI and link it to the project so scripts run with the
deployed env vars:
```
npm i -g @railway/cli
railway login
railway link
```
From `backend/`, using the local `evenv` (already has torch/gdal/geopandas):
```
evenv/python.exe -m railway run -- python scripts/backfill.py 90
```
Then generate + materialize the grid against the live API:
```
curl -X POST https://<your-app>.up.railway.app/grid/generate
curl -X POST https://<your-app>.up.railway.app/grid/materialize
```
Cubes build on the hourly scheduler (`:25`), or trigger immediately:
```
railway run -- python scripts/build_and_train.py <city_slug> 0
```
(0 epochs — this just builds cubes; the committed checkpoints already serve
forecasts without retraining.)

## 5. Vercel (frontend)

1. vercel.com → **New Project** → import this repo → **Root Directory** =
   `frontend` (Next 14 auto-detected).
2. Env vars:
   ```
   NEXT_PUBLIC_API_BASE_URL=https://<your-app>.up.railway.app
   NEXT_PUBLIC_MAPBOX_TOKEN=<token>
   ```
3. Deploy → copy the `*.vercel.app` domain → back on Railway, set
   `BACKEND_CORS_ORIGINS=https://<your-vercel-domain>` (comma-separate to
   keep `http://localhost:3000` for local dev) → redeploy the backend.

## Verify

- `GET https://<app>.up.railway.app/health` → `{"status": "ok", ...}`
- `GET https://<app>.up.railway.app/forecast/grid` → non-empty cells, not
  all-NaN
- Vercel URL loads the map with live data, no CORS errors in the browser
  console
- `psql "<supabase-session-pooler-url>" -c "select postgis_version();"`
  returns a version

## Costs / limits to watch

- **Railway**: free Trial is a one-time $5 credit for 30 days, then $1/mo;
  Hobby is $5/mo flat + overage. Only the backend service is metered here
  (Postgres/Redis live elsewhere), which keeps usage down to roughly one
  always-on container.
- **Supabase free**: 500MB DB storage — fine for readings/grid/agent-run
  tables; cubes live on the Railway volume, not in Postgres, so they don't
  count against this.
- **Upstash free**: 500K commands/mo, 10GB bandwidth — far more than an
  hourly-refresh cache needs.
- Do not train on Railway. Retrain locally and commit the new
  `backend/checkpoints/*.pt` (already git-tracked, ships in the Docker
  image automatically).
