from __future__ import annotations

import math
from typing import Any


MISSING_OR_NON_NUMERIC = 'missing_or_non_numeric'
OUT_OF_RANGE = 'out_of_range'
DISTANCE_THRESHOLD_EXCEEDED = 'distance_threshold_exceeded'


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_lat_lon(lat: Any, lon: Any) -> bool:
    lat_f = _coerce_float(lat)
    lon_f = _coerce_float(lon)
    if lat_f is None or lon_f is None:
        return False
    return -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def flag_geo_suspects(
    rows: list[dict[str, Any]],
    lat_col: str,
    lon_col: str,
    threshold_km: float = 25,
) -> list[dict[str, Any]]:
    flagged: list[dict[str, Any]] = []
    prev_valid_coord: tuple[float, float] | None = None

    for row in rows:
        out = dict(row)
        reasons: list[str] = []
        lat_raw = row.get(lat_col)
        lon_raw = row.get(lon_col)
        lat = _coerce_float(lat_raw)
        lon = _coerce_float(lon_raw)
        distance_km: float | None = None

        if lat is None or lon is None:
            reasons.append(MISSING_OR_NON_NUMERIC)
        elif not validate_lat_lon(lat, lon):
            reasons.append(OUT_OF_RANGE)
        else:
            if prev_valid_coord is not None:
                distance_km = haversine_km(prev_valid_coord[0], prev_valid_coord[1], lat, lon)
                if distance_km >= float(threshold_km):
                    reasons.append(DISTANCE_THRESHOLD_EXCEEDED)
            prev_valid_coord = (lat, lon)

        out['is_suspect'] = bool(reasons)
        out['suspect_reason'] = '|'.join(reasons)
        out['distance_km'] = round(distance_km, 3) if distance_km is not None else None
        flagged.append(out)

    return flagged
