"""
SQLAlchemy engine/session wiring, shared by every module that touches Postgres.

Step 2 tables (raw ingestion) are plain lat/lon columns — no PostGIS geometry
needed yet. Step 3 introduces geometry columns for the 1km grid and will add
GeoAlchemy2 `Geometry` types alongside these tables, not instead of them.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

connect_args = {}
if settings.database_url.startswith("postgresql"):
    connect_args["options"] = "-c search_path=public,extensions"

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables that don't exist yet. Called on app startup in dev;
    a real deploy would use Alembic migrations instead."""
    from app.agents import models as agent_models  # noqa: F401
    from app.features import models as feature_models  # noqa: F401
    from app.geospatial import models as geospatial_models  # noqa: F401
    from app.ingestion import models  # noqa: F401  (registers tables on Base)

    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis SCHEMA extensions"))

    Base.metadata.create_all(bind=engine)
    _apply_column_migrations()


# create_all only creates missing tables — it never alters existing ones, so
# columns added to a model after its table first shipped need an explicit
# ALTER. Postgres-only (tests build their SQLite schema fresh via create_all).
_COLUMN_MIGRATIONS = [
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'new'",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(128)",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMPTZ",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS inspected_at TIMESTAMPTZ",
    "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ",
]


def _apply_column_migrations() -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for stmt in _COLUMN_MIGRATIONS:
            conn.execute(text(stmt))
