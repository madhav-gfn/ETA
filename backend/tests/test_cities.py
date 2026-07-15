import pytest

from app.ingestion.cities import DEFAULT_CITY, get_city


def test_default_city_resolves():
    city = get_city()
    assert city.slug == DEFAULT_CITY
    assert city.display_name == "Delhi NCR"
    min_lon, min_lat, max_lon, max_lat = city.bbox
    assert min_lon < max_lon
    assert min_lat < max_lat


def test_unknown_city_raises():
    with pytest.raises(ValueError, match="Unknown city"):
        get_city("atlantis")
