"""Haversine great-circle distance for solver distance-aware tie-break."""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from app.core.models import GeoPoint

EARTH_RADIUS_KM = 6371.0


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two GeoJSON Points, in kilometers.

    GeoJSON ordering is [lng, lat]. Returns 0.0 if either point lacks
    coordinates — callers should treat missing-location pairs as
    distance-unknown rather than infer proximity.
    """
    if a.lat is None or a.lng is None or b.lat is None or b.lng is None:
        return 0.0

    lat1, lng1 = radians(a.lat), radians(a.lng)
    lat2, lng2 = radians(b.lat), radians(b.lng)

    dlat = lat2 - lat1
    dlng = lng2 - lng1

    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def distance_km_or_none(
    a: GeoPoint | None, b: GeoPoint | None
) -> float | None:
    """Distance in km between two optional GeoPoints; None if either is missing.

    Use this when the caller needs to distinguish "0 km because same location"
    from "0 km because we don't know" — the solver penalizes only the former.
    """
    if a is None or b is None:
        return None
    if a.lat is None or b.lat is None:
        return None
    return haversine_km(a, b)
