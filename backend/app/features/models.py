"""Step 4 manifest table — one row per persisted feature cube; the tensors
themselves live on disk as .npy (too large/columnar for Postgres rows)."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeatureCubeManifest(Base):
    __tablename__ = "feature_cube_manifest"
    __table_args__ = (
        UniqueConstraint("city_slug", "timestep", name="uq_cube_city_time"),
        Index("ix_cube_city_time", "city_slug", "timestep"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    timestep: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    channels: Mapped[str] = mapped_column(String(512), nullable=False)  # comma-separated
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    n_cols: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
