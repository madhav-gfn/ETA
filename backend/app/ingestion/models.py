"""
Raw ingestion tables — one per data modality from the research report's
Table 2, plus a run-log table so `/ingestion/status` has something to report.

These store normalized-but-ungridded records. Step 3's geospatial grid engine
reads from these tables and writes gridded/interpolated state elsewhere; nothing
here has PostGIS geometry columns on purpose — that's introduced alongside the
grid, not before it's needed.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CAAQMSReading(Base):
    """Hourly ground-sensor readings, pulled via the OpenAQ SDK (Section 1.1)."""

    __tablename__ = "caaqms_readings"
    __table_args__ = (
        UniqueConstraint("sensor_id", "measured_at", name="uq_caaqms_sensor_time"),
        Index("ix_caaqms_city_time", "city_slug", "measured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sensor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    station_name: Mapped[str] = mapped_column(String(256), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    parameter: Mapped[str] = mapped_column(String(16), nullable=False)  # pm25, pm10, no2, so2, co, o3
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_interpolated: Mapped[bool] = mapped_column(default=False)  # gap-filled per 1.1's <3hr rule
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FireDetection(Base):
    """NASA FIRMS thermal anomaly detections (Section 1.3)."""

    __tablename__ = "fire_detections"
    __table_args__ = (
        UniqueConstraint(
            "latitude", "longitude", "acq_date", "acq_time", "satellite",
            name="uq_fire_detection",
        ),
        Index("ix_fire_city_time", "city_slug", "acq_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)  # "l"/"n"/"h" (VIIRS) or 0-100 (MODIS)
    frp: Mapped[float] = mapped_column(Float, nullable=True)  # Fire Radiative Power, megawatts
    acq_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    acq_time: Mapped[str] = mapped_column(String(4), nullable=False)  # HHMM (UTC)
    satellite: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. VIIRS_SNPP_NRT
    daynight: Mapped[str] = mapped_column(String(1), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class OSMLandUseFeature(Base):
    """OSM Overpass land-use / road vector tags (Section 1.4). Static/monthly pull.

    Stores each tagged element as a point (node or centroid) for now; Step 3/4
    rasterizes these onto the 1km grid to compute road-density and industrial
    land-use-% features.
    """

    __tablename__ = "osm_land_use_features"
    __table_args__ = (
        UniqueConstraint("osm_id", "osm_type", name="uq_osm_element"),
        Index("ix_osm_city_tag", "city_slug", "tag_key", "tag_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    osm_id: Mapped[int] = mapped_column(Integer, nullable=False)
    osm_type: Mapped[str] = mapped_column(String(16), nullable=False)  # node, way, relation
    tag_key: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "landuse", "highway"
    tag_value: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "industrial", "primary"
    latitude: Mapped[float] = mapped_column(Float, nullable=False)  # node coord or way centroid
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Sentinel5PProduct(Base):
    """Sentinel-5P product metadata from the CDSE OData catalog (Section 1.2).

    Step 2 stores catalog metadata only (product id, sensing window, NRTI vs
    OFFL). Downloading + HARP regridding onto the 1km grid is Step 3/4 work,
    matching the research report's data-cube-assembly step.
    """

    __tablename__ = "sentinel5p_products"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_s5p_product_id"),
        Index("ix_s5p_city_type_time", "city_slug", "product_type", "sensing_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)  # CDSE catalog UUID
    product_name: Mapped[str] = mapped_column(String(256), nullable=False)
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)  # L2__NO2___, L2__SO2___
    processing_level: Mapped[str] = mapped_column(String(8), nullable=False)  # NRTI or OFFL
    sensing_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sensing_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    downloaded: Mapped[bool] = mapped_column(default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class IngestionRunLog(Base):
    """One row per puller invocation — backs the `/ingestion/status` route."""

    __tablename__ = "ingestion_run_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # caaqms, firms, osm, sentinel5p
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running, success, failed
    records_ingested: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(String(1024), nullable=True)
