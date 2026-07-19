from datetime import datetime, timedelta, timezone

from app.ingestion.common import Reading, gap_fill_under_3h


def _at(hour_offset: int) -> datetime:
    return datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc) + timedelta(hours=hour_offset)


def test_no_gap_passthrough():
    readings = [Reading(_at(0), 10.0), Reading(_at(1), 12.0), Reading(_at(2), 14.0)]
    result = gap_fill_under_3h(readings)
    assert result == readings


def test_two_hour_gap_is_filled_linearly():
    readings = [Reading(_at(0), 10.0), Reading(_at(2), 30.0)]
    result = gap_fill_under_3h(readings)

    assert len(result) == 3
    assert result[0].value == 10.0
    assert result[0].is_interpolated is False
    assert result[1].measured_at == _at(1)
    assert result[1].value == 20.0
    assert result[1].is_interpolated is True
    assert result[2].value == 30.0


def test_three_hour_gap_is_not_filled():
    """Per Section 1.1: gaps of 3 hours or more are left as gaps."""
    readings = [Reading(_at(0), 10.0), Reading(_at(3), 40.0)]
    result = gap_fill_under_3h(readings)
    assert result == readings


def test_single_reading_passthrough():
    readings = [Reading(_at(0), 10.0)]
    assert gap_fill_under_3h(readings) == readings


def test_empty_list():
    assert gap_fill_under_3h([]) == []
