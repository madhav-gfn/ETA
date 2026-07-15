"""
SQLAlchemy engine/session wiring, shared by every module that touches Postgres.

Step 2 tables (raw ingestion) are plain lat/lon columns — no PostGIS geometry
needed yet. Step 3 introduces geometry columns for the 1km grid and will add
GeoAlchemy2 `Geometry` types alongside these tables, not instead of them.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
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
    from app.ingestion import models  # noqa: F401  (registers tables on Base)

    Base.metadata.create_all(bind=engine)
