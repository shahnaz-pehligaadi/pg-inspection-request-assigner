from app.core.distance import distance_km_or_none, haversine_km
from app.core.models import GeoPoint


def _point(lat: float, lng: float) -> GeoPoint:
    # GeoJSON ordering is [lng, lat].
    return GeoPoint(type="Point", coordinates=[lng, lat])


def test_haversine_zero_for_identical_points():
    p = _point(12.9716, 77.5946)  # Bengaluru
    assert haversine_km(p, p) == 0.0


def test_haversine_bengaluru_to_mysuru_is_about_120_km():
    # Bengaluru
    a = _point(12.9716, 77.5946)
    # Mysuru
    b = _point(12.2958, 76.6394)
    km = haversine_km(a, b)
    assert 115 < km < 130, f"expected ~120 km, got {km}"


def test_haversine_symmetric():
    a = _point(12.9716, 77.5946)
    b = _point(28.6139, 77.2090)  # Delhi
    assert abs(haversine_km(a, b) - haversine_km(b, a)) < 1e-6


def test_haversine_returns_zero_for_missing_coords():
    empty = GeoPoint(type="Point", coordinates=[])
    p = _point(12.9716, 77.5946)
    assert haversine_km(empty, p) == 0.0
    assert haversine_km(p, empty) == 0.0


def test_distance_km_or_none_missing_returns_none():
    p = _point(12.9716, 77.5946)
    assert distance_km_or_none(None, p) is None
    assert distance_km_or_none(p, None) is None
    assert distance_km_or_none(None, None) is None


def test_distance_km_or_none_empty_coords_returns_none():
    p = _point(12.9716, 77.5946)
    empty = GeoPoint(type="Point", coordinates=[])
    assert distance_km_or_none(empty, p) is None
