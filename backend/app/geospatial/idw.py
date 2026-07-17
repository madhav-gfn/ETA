"""
Inverse Distance Weighting interpolation (Step 3, research report Section 3.1).

    Ẑ(x₀) = Σᵢ wᵢ·Zᵢ / Σᵢ wᵢ,   wᵢ = 1 / d(x₀, xᵢ)^p

p = 2 by default (the report's stated typical value). Only sensors within
`search_radius_m` contribute so far-from-station cells don't get falsely
confident estimates; cells with no sensor in radius get no value at all.

Distances are computed in meters on a local equirectangular approximation —
adequate at city scale (<100km) and much faster than geodesics.
"""

import math
from dataclasses import dataclass

DEFAULT_POWER = 2.0
DEFAULT_SEARCH_RADIUS_M = 15_000.0
# A sensor essentially on top of the centroid: avoid a 1/0 weight blow-up.
MIN_DISTANCE_M = 1.0

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class SensorSample:
    latitude: float
    longitude: float
    value: float


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Equirectangular distance in meters."""
    mean_lat = math.radians((lat1 + lat2) / 2)
    dx = math.radians(lon2 - lon1) * math.cos(mean_lat) * EARTH_RADIUS_M
    dy = math.radians(lat2 - lat1) * EARTH_RADIUS_M
    return math.hypot(dx, dy)


def idw_estimate(
    target_lat: float,
    target_lon: float,
    samples: list[SensorSample],
    power: float = DEFAULT_POWER,
    search_radius_m: float = DEFAULT_SEARCH_RADIUS_M,
) -> tuple[float, int] | None:
    """Estimate the value at (target_lat, target_lon).

    Returns (estimate, contributing_sensor_count), or None if no sensor lies
    within the search radius.
    """
    weight_sum = 0.0
    weighted_value_sum = 0.0
    contributing = 0

    for s in samples:
        d = distance_m(target_lat, target_lon, s.latitude, s.longitude)
        if d > search_radius_m:
            continue
        d = max(d, MIN_DISTANCE_M)
        w = 1.0 / (d ** power)
        weight_sum += w
        weighted_value_sum += w * s.value
        contributing += 1

    if contributing == 0:
        return None
    return weighted_value_sum / weight_sum, contributing


def leave_one_out_rmse(
    samples: list[SensorSample],
    power: float = DEFAULT_POWER,
    search_radius_m: float = DEFAULT_SEARCH_RADIUS_M,
) -> tuple[float, int] | None:
    """Hold out each sensor in turn, interpolate its value from the rest, and
    report RMSE over all sensors that had at least one in-radius neighbour.

    Returns (rmse, n_evaluated) or None if no sensor could be evaluated.
    """
    sq_errors = []
    for i, held_out in enumerate(samples):
        rest = samples[:i] + samples[i + 1:]
        est = idw_estimate(
            held_out.latitude, held_out.longitude, rest,
            power=power, search_radius_m=search_radius_m,
        )
        if est is None:
            continue
        sq_errors.append((est[0] - held_out.value) ** 2)

    if not sq_errors:
        return None
    return math.sqrt(sum(sq_errors) / len(sq_errors)), len(sq_errors)
