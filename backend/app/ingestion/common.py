"""
Utilities shared across all four pullers: run-log tracking and the
sub-3-hour linear gap-fill described in the research report's Section 1.1.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.ingestion.models import IngestionRunLog


@dataclass
class Reading:
    """Minimal (timestamp, value) pair — the shape gap-fill operates on,
    independent of which parameter/sensor it came from."""

    measured_at: datetime
    value: float
    is_interpolated: bool = False


def gap_fill_under_3h(readings: list[Reading]) -> list[Reading]:
    """Linearly interpolate gaps under 3 hours in an hourly time series.

    Per Section 1.1: "missing values will be linearly interpolated for gaps
    under a three-hour duration." Gaps of 3 hours or more are left as gaps —
    filling them would fabricate signal the model shouldn't trust.

    Input must be sorted by measured_at and assumed hourly-cadence; this is
    the raw-per-sensor series before it's written to the DB.
    """
    if len(readings) < 2:
        return readings

    filled: list[Reading] = [readings[0]]
    for prev, curr in zip(readings, readings[1:]):
        gap = curr.measured_at - prev.measured_at
        hourly_gap = timedelta(hours=1)
        if hourly_gap < gap < timedelta(hours=3):
            missing_hours = int(gap / hourly_gap) - 1
            for step in range(1, missing_hours + 1):
                frac = step / (missing_hours + 1)
                interpolated_value = prev.value + frac * (curr.value - prev.value)
                filled.append(
                    Reading(
                        measured_at=prev.measured_at + hourly_gap * step,
                        value=interpolated_value,
                        is_interpolated=True,
                    )
                )
        filled.append(curr)
    return filled


@contextmanager
def track_run(db: Session, source: str, city_slug: str) -> Iterator[IngestionRunLog]:
    """Wraps a puller invocation with an IngestionRunLog row: marks
    running -> success/failed and records how many rows landed.

    Usage:
        with track_run(db, "firms", "delhi-ncr") as run:
            run.records_ingested = pull_and_store(...)
    """
    run = IngestionRunLog(
        source=source,
        city_slug=city_slug,
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        yield run
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:1024]
        raise
    else:
        run.status = "success"
    finally:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
