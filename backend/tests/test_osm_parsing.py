from app.ingestion.osm_landuse import _build_query, _extract_records, _matched_tag, _tiles


def test_build_query_uses_south_west_north_east_order():
    bbox = (76.84, 28.40, 77.35, 28.88)  # (min_lon, min_lat, max_lon, max_lat)
    query = _build_query(bbox, "landuse", ["industrial", "residential"])
    # Overpass expects (south,west,north,east) i.e. (min_lat,min_lon,max_lat,max_lon)
    assert "28.4,76.84,28.88,77.35" in query
    assert "landuse" in query
    assert "industrial|residential" in query


def test_tiles_cover_bbox_without_gaps():
    bbox = (76.84, 28.40, 77.35, 28.88)
    tiles = _tiles(bbox, n=4)
    assert len(tiles) == 16
    assert min(t[0] for t in tiles) == bbox[0]
    assert max(t[2] for t in tiles) == bbox[2]
    assert min(t[1] for t in tiles) == bbox[1]
    assert max(t[3] for t in tiles) == bbox[3]


def test_matched_tag_landuse():
    assert _matched_tag({"landuse": "industrial"}) == ("landuse", "industrial")


def test_matched_tag_highway():
    assert _matched_tag({"highway": "trunk"}) == ("highway", "trunk")


def test_matched_tag_none():
    assert _matched_tag({"amenity": "hospital"}) == (None, None)


def test_extract_records_from_way_with_center():
    elements = [
        {
            "type": "way",
            "id": 123,
            "tags": {"landuse": "industrial"},
            "center": {"lat": 28.6, "lon": 77.2},
        },
        {
            "type": "way",
            "id": 456,
            "tags": {"amenity": "school"},  # not a tracked tag, should be skipped
            "center": {"lat": 28.7, "lon": 77.3},
        },
    ]
    records = _extract_records(elements)
    assert len(records) == 1
    assert records[0]["osm_id"] == 123
    assert records[0]["tag_key"] == "landuse"
    assert records[0]["latitude"] == 28.6


def test_extract_records_from_node():
    elements = [
        {"type": "node", "id": 789, "tags": {"highway": "primary"}, "lat": 28.5, "lon": 77.1},
    ]
    records = _extract_records(elements)
    assert len(records) == 1
    assert records[0]["osm_type"] == "node"
    assert records[0]["tag_value"] == "primary"
