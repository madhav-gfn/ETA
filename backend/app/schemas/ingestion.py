"""Response models for the ingestion API routes."""

from datetime import datetime

from pydantic import BaseModel


class IngestionRunResult(BaseModel):
    source: str
    city_slug: str
    records_ingested: int
    status: str


class IngestionRunLogOut(BaseModel):
    id: int
    source: str
    city_slug: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    records_ingested: int
    error_message: str | None

    model_config = {"from_attributes": True}


class CAAQMSReadingOut(BaseModel):
    station_name: str
    latitude: float
    longitude: float
    parameter: str
    value: float
    unit: str
    measured_at: datetime
    is_interpolated: bool

    model_config = {"from_attributes": True}
