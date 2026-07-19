"""
Sentinel-5P TROPOMI product-metadata ingestion via the Copernicus Data Space
Ecosystem (CDSE) OData catalog (Section 1.2).

Step 2 scope: authenticate, query the catalog for NO2/SO2 products
intersecting the city bbox, and record product metadata (id, sensing
window, NRTI vs OFFL). Actually downloading the NetCDF and regridding it
onto the 1km grid via HARP's bin_spatial (per the research report's
Satellite_S5P / sentinel5P-automated reference repos) is Step 3/4 work —
that's where the QA>0.75 filtering and RBF regridding happens, once the
grid this data gets projected onto actually exists.

Auth: OAuth2 password grant against CDSE's Keycloak realm.
Catalog: OData v1 Products endpoint, filtered by Collection/Name eq
'SENTINEL-5P', product type (contains(Name, 'L2__NO2___')), and a
geography intersects filter for the bbox.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import get_settings
from app.ingestion.cities import CityBounds, get_city
from app.ingestion.models import Sentinel5PProduct
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

# Product types straight from Section 1.2: "L2__NO2___ for Nitrogen Dioxide,
# L2__SO2___ for Sulfur Dioxide".
DEFAULT_PRODUCT_TYPES = ["L2__NO2___", "L2__SO2___"]


async def _get_access_token(client: httpx.AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": "cdse-public",
            "username": username,
            "password": password,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _bbox_to_wkt_polygon(bbox: tuple[float, float, float, float]) -> str:
    min_lon, min_lat, max_lon, max_lat = bbox
    corners = [
        (min_lon, min_lat),
        (max_lon, min_lat),
        (max_lon, max_lat),
        (min_lon, max_lat),
        (min_lon, min_lat),
    ]
    coord_str = ", ".join(f"{lon} {lat}" for lon, lat in corners)
    return f"POLYGON(({coord_str}))"


def _build_filter(
    bbox: tuple[float, float, float, float], product_type: str, since: datetime
) -> str:
    polygon_wkt = _bbox_to_wkt_polygon(bbox)
    since_str = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return (
        "Collection/Name eq 'SENTINEL-5P' "
        f"and contains(Name,'{product_type}') "
        f"and ContentDate/Start gt {since_str} "
        f"and OData.CSC.Intersects(area=geography'SRID=4326;{polygon_wkt}')"
    )


def _processing_level_from_name(product_name: str) -> str:
    """S5P filenames encode timeliness right after the mission prefix, e.g.
    'S5P_NRTI_L2__NO2____...' or 'S5P_OFFL_L2__SO2____...'."""
    parts = product_name.split("_")
    if len(parts) > 1 and parts[1] in {"NRTI", "OFFL", "RPRO"}:
        return parts[1]
    return "UNKNOWN"


async def pull_sentinel5p_products(
    db: Session,
    city_slug: str = "delhi-ncr",
    product_types: list[str] | None = None,
    lookback_days: int = 3,
) -> int:
    """Queries the CDSE catalog for recent NO2/SO2 products over the city
    bbox and upserts product metadata rows.
    """
    settings = get_settings()
    city: CityBounds = get_city(city_slug)
    product_types = product_types or DEFAULT_PRODUCT_TYPES
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    total_written = 0
    async with httpx.AsyncClient() as client:
        token = await _get_access_token(
            client, settings.copernicus_cdse_username, settings.copernicus_cdse_password
        )
        headers = {"Authorization": f"Bearer {token}"}

        for product_type in product_types:
            filter_str = _build_filter(city.bbox, product_type, since)
            resp = await client.get(
                CATALOG_URL,
                params={"$filter": filter_str, "$top": 100},
                headers=headers,
                timeout=60.0,
            )
            resp.raise_for_status()
            products = resp.json().get("value", [])

            for product in products:
                _upsert_product(db, city_slug=city.slug, product_type=product_type, product=product)
                total_written += 1

    db.commit()
    logger.info("Sentinel-5P ingestion for %s wrote %d rows", city_slug, total_written)
    return total_written


def _upsert_product(db: Session, *, city_slug: str, product_type: str, product: dict) -> None:
    content_date = product.get("ContentDate", {})
    stmt = (
        pg_insert(Sentinel5PProduct)
        .values(
            city_slug=city_slug,
            product_id=product["Id"],
            product_name=product["Name"],
            product_type=product_type,
            processing_level=_processing_level_from_name(product["Name"]),
            sensing_start=content_date.get("Start"),
            sensing_end=content_date.get("End"),
        )
        .on_conflict_do_nothing(index_elements=[Sentinel5PProduct.product_id])
    )
    db.execute(stmt)
