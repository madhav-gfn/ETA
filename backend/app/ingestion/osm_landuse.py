"""
OSM urban-morphology ingestion via the Overpass API (Section 1.4) — static
vector data (industrial/residential land-use polygons, primary/trunk roads)
used later for Land Use Regression (LUR) feature engineering in Step 4.

No API key required. This is a monthly static batch pull per Section 1.4's
"Polling Logic", not a scheduled hourly job like the other three pullers.
"""

import logging

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.ingestion.cities import CityBounds, get_city
from app.ingestion.models import OSMLandUseFeature

logger = logging.getLogger(__name__)

# Ordered failover list — overpass-api.de intermittently 406s entire networks,
# so a working mirror must not depend on one host.
OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

# Tag filters straight from Section 1.4: "landuse=industrial, landuse=residential,
# and highway=primary or highway=trunk are extracted to map road networks and
# factory zones".
LANDUSE_VALUES = ["industrial", "residential"]
HIGHWAY_VALUES = ["primary", "trunk"]


def _build_query(
    bbox: tuple[float, float, float, float], tag_key: str, values: list[str]
) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    # Overpass bbox order is (south, west, north, east) — opposite of ours.
    overpass_bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    value_filter = "|".join(values)
    return f"""
[out:json][timeout:120];
way["{tag_key}"~"^({value_filter})$"]({overpass_bbox});
out center;
""".strip()


def _tiles(
    bbox: tuple[float, float, float, float], n: int = 4
) -> list[tuple[float, float, float, float]]:
    """Split a bbox into n×n tiles — full-NCR (and even quadrant) Overpass
    queries 504 at the gateway; 1/16-size tiles complete reliably."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_step = (max_lon - min_lon) / n
    lat_step = (max_lat - min_lat) / n
    return [
        (min_lon + i * lon_step, min_lat + j * lat_step,
         min_lon + (i + 1) * lon_step, min_lat + (j + 1) * lat_step)
        for i in range(n) for j in range(n)
    ]


def _extract_records(elements: list[dict]) -> list[dict]:
    records = []
    for el in elements:
        tags = el.get("tags", {})
        tag_key, tag_value = _matched_tag(tags)
        if tag_key is None:
            continue

        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")

        if lat is None or lon is None:
            continue

        records.append(
            {
                "osm_id": el["id"],
                "osm_type": el["type"],
                "tag_key": tag_key,
                "tag_value": tag_value,
                "latitude": lat,
                "longitude": lon,
            }
        )
    return records


def _matched_tag(tags: dict) -> tuple[str | None, str | None]:
    if tags.get("landuse") in LANDUSE_VALUES:
        return "landuse", tags["landuse"]
    if tags.get("highway") in HIGHWAY_VALUES:
        return "highway", tags["highway"]
    return None, None


async def pull_osm_land_use(db: Session, city_slug: str = "delhi-ncr") -> int:
    """Runs the Overpass QL query for the city bbox and upserts matched
    land-use/road elements. Safe to re-run — static data, idempotent upsert.
    """
    city: CityBounds = get_city(city_slug)

    tag_queries = [("landuse", LANDUSE_VALUES), ("highway", HIGHWAY_VALUES)]
    total = 0
    async with httpx.AsyncClient() as client:
        for tile in _tiles(city.bbox):
            for tag_key, values in tag_queries:
                query = _build_query(tile, tag_key, values)
                payload = await _post_overpass(client, query)
                records = _extract_records(payload.get("elements", []))
                for record in records:
                    _upsert_feature(db, city_slug=city.slug, record=record)
                total += len(records)
                db.commit()  # commit per chunk so a late failure keeps earlier tiles

    logger.info("OSM ingestion for %s wrote %d rows", city_slug, total)
    return total


async def _post_overpass(client: httpx.AsyncClient, query: str) -> dict:
    last_exc: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            resp = await client.post(url, data={"data": query}, timeout=200.0)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Overpass endpoint %s failed: %s", url, exc)
            last_exc = exc
    raise RuntimeError("All Overpass endpoints failed") from last_exc


def _upsert_feature(db: Session, *, city_slug: str, record: dict) -> None:
    stmt = (
        pg_insert(OSMLandUseFeature)
        .values(city_slug=city_slug, **record)
        .on_conflict_do_update(
            index_elements=[OSMLandUseFeature.osm_id, OSMLandUseFeature.osm_type],
            set_={
                "tag_key": record["tag_key"],
                "tag_value": record["tag_value"],
                "latitude": record["latitude"],
                "longitude": record["longitude"],
            },
        )
    )
    db.execute(stmt)
