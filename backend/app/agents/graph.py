"""
Step 6 — multi-agent enforcement pipeline (research report Section 4).

Three agents run as a LangGraph state machine:
  1. Monitoring       — scans the latest gridded PM2.5 state (or the model
                        forecast) for WHO-threshold anomalies; a synthetic
                        anomaly can be injected for demos and is flagged.
  2. Source Attribution — "Environmental Forensics Expert": upwind FIRMS
                        fires within 50km, industrial land-use density and
                        highway density in the target cell, current wind.
                        Deterministic scoring produces category+confidence;
                        the LLM (Groq) writes the expert rationale on top.
  3. Enforcement      — "Municipal Dispatch Coordinator": ranks cells by
                        pollutant magnitude × residential density, chains the
                        top cells into a nearest-neighbour patrol route.

Every LLM call has a deterministic fallback so the pipeline always completes.
"""

import logging
import math
from datetime import datetime, timezone
from typing import TypedDict

import numpy as np
from langgraph.graph import END, StateGraph
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.llm import complete
from app.agents.schemas import (
    AgentRunResult,
    AnomalyAlert,
    AttributionResult,
    EnforcementPlan,
    EvidenceItem,
    PatrolStop,
)
from app.geospatial.idw import distance_m, distance_m_vec
from app.geospatial.models import GridCell, GridReading
from app.ingestion.meteo_openmeteo import latest_meteo
from app.ingestion.models import FireDetection, OSMLandUseFeature

logger = logging.getLogger(__name__)

WHO_PM25_THRESHOLD = 150.0  # µg/m³ — configurable anomaly trigger
UPWIND_RADIUS_M = 50_000.0
UPWIND_CONE_DEG = 60.0  # half-angle of the upwind sector


class AgentState(TypedDict, total=False):
    db: Session
    city_slug: str
    threshold: float
    synthetic_grid_id: int | None
    alert: AnomalyAlert | None
    attribution: AttributionResult | None
    plan: EnforcementPlan | None


# --- 1. Monitoring agent ----------------------------------------------------

def monitoring_node(state: AgentState) -> AgentState:
    db, city = state["db"], state["city_slug"]
    threshold = state.get("threshold", WHO_PM25_THRESHOLD)

    latest_ts = db.execute(
        select(func.max(GridReading.measured_at)).where(
            GridReading.city_slug == city, GridReading.parameter == "pm25"
        )
    ).scalar_one_or_none()
    if latest_ts is None:
        state["alert"] = None
        return state

    q = (
        select(GridReading, GridCell)
        .join(GridCell, GridCell.grid_id == GridReading.grid_id)
        .where(
            GridReading.city_slug == city,
            GridReading.parameter == "pm25",
            GridReading.measured_at == latest_ts,
        )
    )
    rows = db.execute(q).all()

    synthetic_gid = state.get("synthetic_grid_id")
    if synthetic_gid is not None:
        match = [(r, c) for r, c in rows if c.grid_id == synthetic_gid]
        if not match:
            state["alert"] = None
            return state
        reading, cell = match[0]
        state["alert"] = AnomalyAlert(
            grid_id=cell.grid_id, row_idx=cell.row_idx, col_idx=cell.col_idx,
            centroid_lat=cell.centroid_lat, centroid_lon=cell.centroid_lon,
            forecast_value=max(reading.value, threshold + 75.0),  # amplified for the drill
            threshold=threshold, timestamp=latest_ts, synthetic=True,
        )
        return state

    worst = max(rows, key=lambda rc: rc[0].value, default=None)
    if worst is None or worst[0].value < threshold:
        state["alert"] = None
        return state
    reading, cell = worst
    state["alert"] = AnomalyAlert(
        grid_id=cell.grid_id, row_idx=cell.row_idx, col_idx=cell.col_idx,
        centroid_lat=cell.centroid_lat, centroid_lon=cell.centroid_lon,
        forecast_value=reading.value, threshold=threshold, timestamp=latest_ts,
    )
    return state


# --- 2. Source attribution agent -------------------------------------------

def _bearing_deg_vec(lat1: float, lon1: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Initial bearing (degrees clockwise from north) from one point to many."""
    lat1r = math.radians(lat1)
    latsr = np.deg2rad(lats)
    dlon = np.deg2rad(lons - lon1)
    y = np.sin(dlon) * np.cos(latsr)
    x = math.cos(lat1r) * np.sin(latsr) - math.sin(lat1r) * np.cos(latsr) * np.cos(dlon)
    return (np.degrees(np.arctan2(y, x)) + 360) % 360


def _bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """Lat/lon bounding box enclosing a radius — a cheap SQL prefilter so the
    precise distance check runs over dozens of rows, not the whole city."""
    dlat = radius_m / 111_000.0
    dlon = radius_m / (111_000.0 * max(math.cos(math.radians(lat)), 0.1))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def _count_within(
    src_lats: np.ndarray, src_lons: np.ndarray,
    pt_lats: np.ndarray, pt_lons: np.ndarray,
    radius_m: float, chunk: int = 512,
) -> np.ndarray:
    """For each source point, count how many of the points fall within
    radius_m. Chunked broadcasting keeps the (M, N) distance matrix bounded."""
    counts = np.zeros(len(src_lats), dtype=np.int64)
    if len(pt_lats) == 0:
        return counts
    for i in range(0, len(src_lats), chunk):
        d = distance_m_vec(
            src_lats[i : i + chunk, None], src_lons[i : i + chunk, None],
            pt_lats[None, :], pt_lons[None, :],
        )
        counts[i : i + chunk] = (d <= radius_m).sum(axis=1)
    return counts


def attribution_node(state: AgentState) -> AgentState:
    alert = state.get("alert")
    if alert is None:
        return state
    db, city = state["db"], state["city_slug"]
    evidence: list[EvidenceItem] = []

    meteo = latest_meteo(db, city)
    wind_from = meteo.wind_direction_deg if meteo and meteo.wind_direction_deg is not None else None
    wind_speed = meteo.wind_speed_kmh if meteo else None
    if wind_from is not None:
        evidence.append(EvidenceItem(
            kind="wind",
            description=f"Wind blowing from {wind_from:.0f}° at {wind_speed or 0:.0f} km/h",
            detail={"direction_from_deg": wind_from, "speed_kmh": wind_speed},
        ))

    # Upwind fires within 50km (research report system prompt) — bbox SQL
    # prefilter, then vectorized distance + bearing checks.
    lat_lo, lat_hi, lon_lo, lon_hi = _bbox(alert.centroid_lat, alert.centroid_lon, UPWIND_RADIUS_M)
    fire_rows = db.execute(
        select(FireDetection.latitude, FireDetection.longitude, FireDetection.frp).where(
            FireDetection.city_slug == city,
            FireDetection.latitude.between(lat_lo, lat_hi),
            FireDetection.longitude.between(lon_lo, lon_hi),
        )
    ).all()
    upwind_frp = 0.0
    upwind_count = 0
    if fire_rows:
        f_lats = np.array([r[0] for r in fire_rows])
        f_lons = np.array([r[1] for r in fire_rows])
        f_frps = np.array([r[2] or 0.0 for r in fire_rows])
        keep = distance_m_vec(alert.centroid_lat, alert.centroid_lon, f_lats, f_lons) <= UPWIND_RADIUS_M
        if wind_from is not None:
            bearings = _bearing_deg_vec(alert.centroid_lat, alert.centroid_lon, f_lats, f_lons)
            diff = np.abs((bearings - wind_from + 180) % 360 - 180)
            keep &= diff <= UPWIND_CONE_DEG
        upwind_frp = float(f_frps[keep].sum())
        upwind_count = int(keep.sum())
    if upwind_count:
        evidence.append(EvidenceItem(
            kind="fire_upwind",
            description=f"{upwind_count} fire detections upwind within 50km, total FRP {upwind_frp:.0f} MW",
            detail={"count": upwind_count, "total_frp_mw": upwind_frp},
        ))

    # OSM context in ~1.5km of the cell centroid.
    lat_lo, lat_hi, lon_lo, lon_hi = _bbox(alert.centroid_lat, alert.centroid_lon, 1_500)
    osm_rows = db.execute(
        select(
            OSMLandUseFeature.tag_key, OSMLandUseFeature.tag_value,
            OSMLandUseFeature.latitude, OSMLandUseFeature.longitude,
        ).where(
            OSMLandUseFeature.city_slug == city,
            OSMLandUseFeature.latitude.between(lat_lo, lat_hi),
            OSMLandUseFeature.longitude.between(lon_lo, lon_hi),
        )
    ).all()
    industrial = highway = 0
    for tag_key, tag_value, o_lat, o_lon in osm_rows:
        if distance_m(alert.centroid_lat, alert.centroid_lon, o_lat, o_lon) <= 1_500:
            if tag_key == "landuse" and tag_value == "industrial":
                industrial += 1
            elif tag_key == "highway":
                highway += 1
    if industrial:
        evidence.append(EvidenceItem(
            kind="industrial_zone",
            description=f"{industrial} industrial land-use polygons within 1.5km",
            detail={"count": industrial},
        ))
    if highway:
        evidence.append(EvidenceItem(
            kind="highway_density",
            description=f"{highway} primary/trunk road segments within 1.5km",
            detail={"count": highway},
        ))

    # Deterministic decision logic (research report Section 4).
    scores = {
        "biomass_burning": min(upwind_frp / 100.0, 1.0),
        "industrial": min(industrial / 10.0, 1.0),
        "vehicular": min(highway / 20.0, 1.0),
    }
    peak_hour = alert.timestamp.astimezone(timezone.utc).hour in (2, 3, 4, 12, 13, 14)  # IST commute ≈ UTC-5:30
    if peak_hour:
        scores["vehicular"] = min(scores["vehicular"] * 1.5, 1.0)
    category = max(scores, key=scores.get)
    confidence = scores[category]
    if confidence < 0.15:
        category, confidence = "mixed/unknown", 0.3

    fallback_rationale = (
        f"Attributed to {category.replace('_', ' ')} "
        f"(scores: biomass {scores['biomass_burning']:.2f}, industrial {scores['industrial']:.2f}, "
        f"vehicular {scores['vehicular']:.2f}) based on "
        + "; ".join(e.description for e in evidence) if evidence else
        f"No strong upwind fire, industrial, or road signal — defaulting to {category}."
    )
    llm_text = complete(
        system=(
            "You are an Environmental Forensics Expert analysing an air quality anomaly "
            "in an Indian metropolis. Given the evidence, explain in 3-4 sentences which "
            "pollution source category is most likely and why. Be specific and cautious."
        ),
        user=(
            f"Anomaly: PM2.5 {alert.forecast_value:.0f} µg/m³ (threshold {alert.threshold:.0f}) "
            f"at grid cell {alert.grid_id} ({alert.centroid_lat:.3f}, {alert.centroid_lon:.3f}).\n"
            f"Evidence: {[e.description for e in evidence]}\n"
            f"Deterministic scores: {scores}. Chosen category: {category}."
        ),
    )

    state["attribution"] = AttributionResult(
        source_category=category,
        confidence=round(confidence, 2),
        rationale=llm_text or fallback_rationale,
        evidence=evidence,
        llm_used=llm_text is not None,
    )
    return state


# --- 3. Enforcement prioritization agent ------------------------------------

def enforcement_node(state: AgentState) -> AgentState:
    alert = state.get("alert")
    if alert is None:
        return state
    db, city = state["db"], state["city_slug"]

    latest_ts = alert.timestamp
    rows = db.execute(
        select(GridReading, GridCell)
        .join(GridCell, GridCell.grid_id == GridReading.grid_id)
        .where(
            GridReading.city_slug == city,
            GridReading.parameter == "pm25",
            GridReading.measured_at == latest_ts,
        )
    ).all()

    # Residential density per cell from OSM — one vectorized pass over
    # (cells × residential features) instead of a Python distance loop per
    # cell, which was tens of millions of scalar ops per run.
    res_rows = db.execute(
        select(OSMLandUseFeature.latitude, OSMLandUseFeature.longitude).where(
            OSMLandUseFeature.city_slug == city,
            OSMLandUseFeature.tag_key == "landuse",
            OSMLandUseFeature.tag_value == "residential",
        )
    ).all()
    res_lats = np.array([r[0] for r in res_rows])
    res_lons = np.array([r[1] for r in res_rows])
    cell_lats = np.array([cell.centroid_lat for _, cell in rows])
    cell_lons = np.array([cell.centroid_lon for _, cell in rows])
    res_counts = _count_within(cell_lats, cell_lons, res_lats, res_lons, 1_500)

    scored = []
    for (reading, cell), res in zip(rows, res_counts):
        res = int(res)
        score = reading.value * (1 + res)  # AQI magnitude × residential density
        scored.append((score, reading, cell, res))
    scored.sort(key=lambda s: s[0], reverse=True)
    top = scored[:5]

    # Nearest-neighbour chain from the anomaly cell = patrol route.
    stops: list[PatrolStop] = []
    remaining = list(top)
    cur_lat, cur_lon = alert.centroid_lat, alert.centroid_lon
    while remaining:
        remaining.sort(
            key=lambda s: distance_m(cur_lat, cur_lon, s[2].centroid_lat, s[2].centroid_lon)
        )
        score, reading, cell, res = remaining.pop(0)
        stops.append(PatrolStop(
            grid_id=cell.grid_id,
            centroid_lat=cell.centroid_lat,
            centroid_lon=cell.centroid_lon,
            priority_score=round(score, 1),
            reason=f"PM2.5 {reading.value:.0f} µg/m³, {res} residential zones within 1.5km",
        ))
        cur_lat, cur_lon = cell.centroid_lat, cell.centroid_lon

    total_km = sum(
        distance_m(stops[i].centroid_lat, stops[i].centroid_lon,
                   stops[i + 1].centroid_lat, stops[i + 1].centroid_lon)
        for i in range(len(stops) - 1)
    ) / 1000.0
    fallback = (
        f"Patrol route covers {len(stops)} highest-exposure cells "
        f"(~{total_km:.1f} km), ordered nearest-neighbour from the anomaly site. "
        f"Priority = PM2.5 magnitude × residential density."
    )
    attribution = state.get("attribution")
    llm_text = complete(
        system=(
            "You are a Municipal Dispatch Coordinator for a pollution control board in India. "
            "Write a 3-sentence dispatch instruction for an inspector patrol, referencing the "
            "attributed source and what inspectors should verify at the stops."
        ),
        user=(
            f"Attributed source: {attribution.source_category if attribution else 'unknown'}.\n"
            f"Stops: {[(s.grid_id, s.reason) for s in stops]}\nTotal distance ~{total_km:.1f} km."
        ),
    )

    state["plan"] = EnforcementPlan(
        ranked_cells=stops,
        route_summary=f"{len(stops)} stops, ~{total_km:.1f} km",
        rationale=llm_text or fallback,
        llm_used=llm_text is not None,
    )
    return state


# --- graph wiring -----------------------------------------------------------

def _after_monitoring(state: AgentState) -> str:
    return "attribute" if state.get("alert") is not None else END


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("monitor", monitoring_node)
    g.add_node("attribute", attribution_node)
    g.add_node("enforce", enforcement_node)
    g.set_entry_point("monitor")
    g.add_conditional_edges("monitor", _after_monitoring)
    g.add_edge("attribute", "enforce")
    g.add_edge("enforce", END)
    return g.compile()


_GRAPH = None


def run_agents(
    db: Session,
    city_slug: str = "delhi-ncr",
    threshold: float = WHO_PM25_THRESHOLD,
    synthetic_grid_id: int | None = None,
) -> AgentRunResult | None:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    out = _GRAPH.invoke({
        "db": db, "city_slug": city_slug, "threshold": threshold,
        "synthetic_grid_id": synthetic_grid_id,
    })
    if out.get("alert") is None:
        return None
    return AgentRunResult(
        alert=out["alert"],
        attribution=out["attribution"],
        plan=out["plan"],
        completed_at=datetime.now(timezone.utc),
    )
