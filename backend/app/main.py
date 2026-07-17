"""
FastAPI application entrypoint.

Step 1 wired up: app instance, CORS for the Next.js frontend, and the health
route. Step 2 adds: DB table creation on startup, the ingestion router, and
the APScheduler-driven background pullers. Subsequent steps register their
own routers here:
  Step 3 -> app/api/routes/grid.py
  Step 5 -> app/api/routes/forecast.py
  Step 6 -> app/api/routes/agents.py
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import advisory, agents, features, forecast, grid, health, ingestion
from app.core.config import get_settings
from app.core.db import init_db
from app.ingestion.scheduler import start_scheduler, stop_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In tests, fixtures own their own (SQLite) schema via dependency
    # override, and the scheduler would otherwise try to hit live external
    # APIs on a timer — both are skipped when ENVIRONMENT=test.
    if settings.environment != "test":
        init_db()
        start_scheduler()
    yield
    if settings.environment != "test":
        stop_scheduler()


app = FastAPI(
    title="UrbanAir Intel API",
    description="AI-powered Urban Air Quality Intelligence platform backend.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(ingestion.router)
app.include_router(grid.router)
app.include_router(features.router)
app.include_router(forecast.router)
app.include_router(agents.router)
app.include_router(advisory.router)


@app.get("/")
def root() -> dict:
    return {"message": "UrbanAir Intel API — see /docs for available endpoints."}
