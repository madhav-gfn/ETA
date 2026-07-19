"""
Manual ingestion triggers + read endpoints. The scheduler (Step 2's
scheduler.py) runs these automatically at their proper cadence; these routes
exist so a puller can be triggered on demand — useful for the demo and for
backfilling before the scheduler has had a chance to run.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.ingestion.caaqms_openaq import latest_readings, pull_caaqms_readings
from app.ingestion.cities import DEFAULT_CITY
from app.ingestion.common import track_run
from app.ingestion.firms_fires import pull_fire_detections
from app.ingestion.meteo_openmeteo import backfill_meteo, pull_meteo
from app.ingestion.models import (
    CAAQMSReading,
    FireDetection,
    IngestionRunLog,
    MeteoReading,
    OSMLandUseFeature,
    Sentinel5PProduct,
)
from app.ingestion.osm_landuse import pull_osm_land_use
from app.ingestion.sentinel5p import pull_sentinel5p_products
from app.schemas.ingestion import CAAQMSReadingOut, IngestionRunLogOut, IngestionRunResult

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

# source -> (raw table, column marking how fresh its data is)
SOURCE_TABLES = {
    "caaqms": (CAAQMSReading, CAAQMSReading.measured_at),
    "firms": (FireDetection, FireDetection.ingested_at),
    "osm": (OSMLandUseFeature, OSMLandUseFeature.fetched_at),
    "sentinel5p": (Sentinel5PProduct, Sentinel5PProduct.fetched_at),
    "meteo": (MeteoReading, MeteoReading.measured_at),
}


@router.post("/caaqms/run", response_model=IngestionRunResult)
def trigger_caaqms(
    city_slug: str = DEFAULT_CITY, hours_back: int = 1, db: Session = Depends(get_db)
):
    """hours_back<=2 pulls each location's latest values (hourly cadence);
    larger values fetch per-sensor hourly history — the backfill path."""
    with track_run(db, "caaqms", city_slug) as run:
        run.records_ingested = pull_caaqms_readings(db, city_slug, hours_back=hours_back)
    return IngestionRunResult(
        source="caaqms", city_slug=city_slug, records_ingested=run.records_ingested, status=run.status
    )


@router.post("/firms/run", response_model=IngestionRunResult)
async def trigger_firms(city_slug: str = DEFAULT_CITY, db: Session = Depends(get_db)):
    with track_run(db, "firms", city_slug) as run:
        run.records_ingested = await pull_fire_detections(db, city_slug)
    return IngestionRunResult(
        source="firms", city_slug=city_slug, records_ingested=run.records_ingested, status=run.status
    )


@router.post("/osm/run", response_model=IngestionRunResult)
async def trigger_osm(city_slug: str = DEFAULT_CITY, db: Session = Depends(get_db)):
    with track_run(db, "osm", city_slug) as run:
        run.records_ingested = await pull_osm_land_use(db, city_slug)
    return IngestionRunResult(
        source="osm", city_slug=city_slug, records_ingested=run.records_ingested, status=run.status
    )


@router.post("/sentinel5p/run", response_model=IngestionRunResult)
async def trigger_sentinel5p(city_slug: str = DEFAULT_CITY, db: Session = Depends(get_db)):
    with track_run(db, "sentinel5p", city_slug) as run:
        run.records_ingested = await pull_sentinel5p_products(db, city_slug)
    return IngestionRunResult(
        source="sentinel5p", city_slug=city_slug, records_ingested=run.records_ingested, status=run.status
    )


@router.post("/meteo/run", response_model=IngestionRunResult)
async def trigger_meteo(city_slug: str = DEFAULT_CITY, db: Session = Depends(get_db)):
    with track_run(db, "meteo", city_slug) as run:
        run.records_ingested = await pull_meteo(db, city_slug)
    return IngestionRunResult(
        source="meteo", city_slug=city_slug, records_ingested=run.records_ingested, status=run.status
    )


@router.post("/meteo/backfill", response_model=IngestionRunResult)
async def trigger_meteo_backfill(
    city_slug: str = DEFAULT_CITY, days: int = 90, db: Session = Depends(get_db)
):
    with track_run(db, "meteo-backfill", city_slug) as run:
        run.records_ingested = await backfill_meteo(db, city_slug, days)
    return IngestionRunResult(
        source="meteo-backfill", city_slug=city_slug, records_ingested=run.records_ingested, status=run.status
    )


@router.get("/summary")
def ingestion_summary(city_slug: str = DEFAULT_CITY, db: Session = Depends(get_db)):
    """Consolidated per-source pipeline health for the /data dashboard page:
    last run outcome, total rows landed, and how fresh the newest row is."""
    sources = []
    for source, (model, freshness_col) in SOURCE_TABLES.items():
        last_run = db.execute(
            select(IngestionRunLog)
            .where(IngestionRunLog.source == source, IngestionRunLog.city_slug == city_slug)
            .order_by(IngestionRunLog.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        table_rows, latest_data_at = db.execute(
            select(func.count(), func.max(freshness_col)).where(model.city_slug == city_slug)
        ).one()
        sources.append(
            {
                "source": source,
                "table_rows": table_rows,
                "latest_data_at": latest_data_at.isoformat() if latest_data_at else None,
                "last_run": None
                if last_run is None
                else {
                    "started_at": last_run.started_at.isoformat(),
                    "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
                    "status": last_run.status,
                    "records_ingested": last_run.records_ingested,
                    "error_message": last_run.error_message,
                },
            }
        )
    return {"city_slug": city_slug, "sources": sources}


@router.get("/status", response_model=list[IngestionRunLogOut])
def ingestion_status(limit: int = 20, db: Session = Depends(get_db)):
    stmt = select(IngestionRunLog).order_by(IngestionRunLog.started_at.desc()).limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/caaqms/latest", response_model=list[CAAQMSReadingOut])
def caaqms_latest(city_slug: str = DEFAULT_CITY, limit: int = 100, db: Session = Depends(get_db)):
    return latest_readings(db, city_slug, limit)
