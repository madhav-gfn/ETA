"""
Scheduling for the four ingestion pullers, each at the cadence its source
dictates (research report Table 2):
  - CAAQMS/OpenAQ    hourly
  - NASA FIRMS       every 3 hours (satellite overpass latency)
  - Sentinel-5P      daily (NRTI/OFFL catalog refresh)
  - OSM Overpass     monthly (static land-use/road batch)

Runs in-process via APScheduler rather than a separate worker — sufficient
for a hackathon prototype's single-instance deployment. A production
deploy would move this to Celery beat or similar.
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.db import SessionLocal
from app.ingestion.caaqms_openaq import pull_caaqms_readings
from app.ingestion.cities import DEFAULT_CITY
from app.ingestion.common import track_run
from app.ingestion.firms_fires import pull_fire_detections
from app.ingestion.osm_landuse import pull_osm_land_use
from app.ingestion.sentinel5p import pull_sentinel5p_products

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def run_caaqms_job(city_slug: str = DEFAULT_CITY) -> None:
    db = SessionLocal()
    try:
        with track_run(db, "caaqms", city_slug) as run:
            run.records_ingested = await asyncio.to_thread(pull_caaqms_readings, db, city_slug)
    except Exception:
        logger.exception("CAAQMS ingestion job failed")
    finally:
        db.close()


async def run_firms_job(city_slug: str = DEFAULT_CITY) -> None:
    db = SessionLocal()
    try:
        with track_run(db, "firms", city_slug) as run:
            run.records_ingested = await pull_fire_detections(db, city_slug)
    except Exception:
        logger.exception("FIRMS ingestion job failed")
    finally:
        db.close()


async def run_sentinel5p_job(city_slug: str = DEFAULT_CITY) -> None:
    db = SessionLocal()
    try:
        with track_run(db, "sentinel5p", city_slug) as run:
            run.records_ingested = await pull_sentinel5p_products(db, city_slug)
    except Exception:
        logger.exception("Sentinel-5P ingestion job failed")
    finally:
        db.close()


async def run_osm_job(city_slug: str = DEFAULT_CITY) -> None:
    db = SessionLocal()
    try:
        with track_run(db, "osm", city_slug) as run:
            run.records_ingested = await pull_osm_land_use(db, city_slug)
    except Exception:
        logger.exception("OSM ingestion job failed")
    finally:
        db.close()


def start_scheduler() -> None:
    scheduler.add_job(run_caaqms_job, IntervalTrigger(hours=1), id="caaqms_hourly", replace_existing=True)
    scheduler.add_job(run_firms_job, IntervalTrigger(hours=3), id="firms_3hourly", replace_existing=True)
    scheduler.add_job(run_sentinel5p_job, IntervalTrigger(hours=24), id="sentinel5p_daily", replace_existing=True)
    scheduler.add_job(run_osm_job, CronTrigger(day=1, hour=3), id="osm_monthly", replace_existing=True)
    scheduler.start()
    logger.info("Ingestion scheduler started: caaqms=1h, firms=3h, sentinel5p=24h, osm=monthly")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
