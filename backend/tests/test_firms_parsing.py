from app.ingestion.firms_fires import _format_area, _parse_firms_csv


def test_format_area_matches_firms_bbox_order():
    bbox = (76.84, 28.40, 77.35, 28.88)
    assert _format_area(bbox) == "76.8400,28.4000,77.3500,28.8800"


def test_parse_viirs_csv():
    raw = (
        "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
        "instrument,confidence,version,bright_ti5,frp,daynight\n"
        "28.7041,77.1025,320.5,0.4,0.4,2026-07-15,0530,N,VIIRS,n,2.0NRT,290.1,12.3,D\n"
    )
    rows = _parse_firms_csv(raw)
    assert len(rows) == 1
    assert rows[0]["latitude"] == "28.7041"
    assert rows[0]["frp"] == "12.3"
    assert rows[0]["confidence"] == "n"


def test_parse_empty_csv_returns_empty_list():
    assert _parse_firms_csv("") == []
