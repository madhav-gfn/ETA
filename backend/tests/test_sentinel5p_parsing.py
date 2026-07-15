from datetime import datetime, timezone

from app.ingestion.sentinel5p import (
    _bbox_to_wkt_polygon,
    _build_filter,
    _processing_level_from_name,
)


def test_bbox_to_wkt_polygon_is_closed_ring():
    bbox = (76.84, 28.40, 77.35, 28.88)
    wkt = _bbox_to_wkt_polygon(bbox)
    assert wkt.startswith("POLYGON((")
    # first and last coordinate pair must match to close the ring
    coords = wkt[len("POLYGON((") : -2].split(", ")
    assert coords[0] == coords[-1]
    assert len(coords) == 5


def test_build_filter_contains_expected_clauses():
    bbox = (76.84, 28.40, 77.35, 28.88)
    since = datetime(2026, 7, 12, tzinfo=timezone.utc)
    filter_str = _build_filter(bbox, "L2__NO2___", since)

    assert "Collection/Name eq 'SENTINEL-5P'" in filter_str
    assert "contains(Name,'L2__NO2___')" in filter_str
    assert "ContentDate/Start gt 2026-07-12T00:00:00.000Z" in filter_str
    assert "OData.CSC.Intersects" in filter_str


def test_processing_level_nrti():
    name = "S5P_NRTI_L2__NO2_____20260715T053000_20260715T054500_12345_03_020400_20260715T063000.nc"
    assert _processing_level_from_name(name) == "NRTI"


def test_processing_level_offl():
    name = "S5P_OFFL_L2__SO2_____20260715T053000_20260715T054500_12345_03_020400_20260715T063000.nc"
    assert _processing_level_from_name(name) == "OFFL"


def test_processing_level_unknown_for_unexpected_format():
    assert _processing_level_from_name("not_a_real_product_name") == "UNKNOWN"
