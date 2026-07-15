"""
City bounding box registry.

Every puller takes a bbox rather than hardcoding a city, so adding a second
demo city (per the PS brief's multi-city ask) is a one-line addition here —
no changes needed in ingestion, grid, or model code.

Bbox format: (min_lon, min_lat, max_lon, max_lat) — WGS84, matches both the
OpenAQ SDK's `bbox` param order and general GIS convention.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CityBounds:
    slug: str
    display_name: str
    bbox: tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    utm_epsg: int  # projected CRS for 1km grid math in Step 3


CITIES: dict[str, CityBounds] = {
    "delhi-ncr": CityBounds(
        slug="delhi-ncr",
        display_name="Delhi NCR",
        bbox=(76.84, 28.40, 77.35, 28.88),
        utm_epsg=32643,  # UTM Zone 43N, matches the research report's North India CRS
    ),
    "mumbai": CityBounds(
        slug="mumbai",
        display_name="Mumbai",
        bbox=(72.77, 18.89, 72.98, 19.28),
        utm_epsg=32643,
    ),
}

DEFAULT_CITY = "delhi-ncr"


def get_city(slug: str = DEFAULT_CITY) -> CityBounds:
    try:
        return CITIES[slug]
    except KeyError as exc:
        raise ValueError(f"Unknown city '{slug}'. Known cities: {list(CITIES)}") from exc
