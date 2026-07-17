"""
Step 3 tables — the shared 1km×1km spatial index (grid_cells) and hourly
interpolated pollutant state per cell (grid_readings).

This is where PostGIS geometry enters the schema: each cell stores its WGS84
polygon so the frontend can draw it and PostGIS can spatially join against it.
"""

from datetime import datetime, timezone

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GridCell(Base):
    """One 1km×1km cell of a city's grid. Generated once per city from its
    bbox projected into the city's UTM zone; re-generation is idempotent."""

    __tablename__ = "grid_cells"
    __table_args__ = (
        UniqueConstraint("city_slug", "row_idx", "col_idx", name="uq_grid_cell_pos"),
        Index("ix_grid_city", "city_slug"),
    )

    grid_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    # row_idx/col_idx give the ConvLSTM its 2D array layout for free (Step 5).
    row_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    col_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    centroid_lat: Mapped[float] = mapped_column(Float, nullable=False)
    centroid_lon: Mapped[float] = mapped_column(Float, nullable=False)
    geom = mapped_column(Geometry(geometry_type="POLYGON", srid=4326), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GridReading(Base):
    """Hourly IDW-interpolated pollutant value at one grid cell centroid."""

    __tablename__ = "grid_readings"
    __table_args__ = (
        UniqueConstraint(
            "grid_id", "parameter", "measured_at", name="uq_grid_reading"
        ),
        Index("ix_grid_readings_city_param_time", "city_slug", "parameter", "measured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grid_id: Mapped[int] = mapped_column(Integer, nullable=False)
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    parameter: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interpolation_method: Mapped[str] = mapped_column(String(16), default="idw")
    contributing_sensor_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
