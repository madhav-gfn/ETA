import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("ENVIRONMENT", "test")

from app.core.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Only the raw ingestion tables use portable column types SQLite can
    # create; the Step 3 grid tables carry a PostGIS Geometry column, so
    # they're excluded here — grid logic is tested at the pure-function level.
    from app.ingestion import models

    ingestion_tables = [
        models.CAAQMSReading.__table__,
        models.FireDetection.__table__,
        models.OSMLandUseFeature.__table__,
        models.Sentinel5PProduct.__table__,
        models.MeteoReading.__table__,
        models.IngestionRunLog.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=ingestion_tables)
    yield engine
    Base.metadata.drop_all(bind=engine, tables=ingestion_tables)


@pytest.fixture()
def db_session(test_engine):
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(test_engine):
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
