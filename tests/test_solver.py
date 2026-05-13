from datetime import datetime, timezone

from app.core.models import GeoPoint, InspectorAvailability, PendingRequest, Slot
from app.core.solver import solve_bucket


def _point(lat: float, lng: float) -> GeoPoint:
    # GeoJSON ordering is [lng, lat].
    return GeoPoint(type="Point", coordinates=[lng, lat])


def make_req(
    rid: str,
    pincode: str,
    time: datetime | None,
    urgency: str = "MEDIUM",
    location: GeoPoint | None = None,
) -> PendingRequest:
    return PendingRequest(
        requestId=rid,
        pincode=pincode,
        preferredTime=time,
        urgencyLevel=urgency,
        status="insp-req-status01",
        location=location,
    )


def make_inspector(
    eid: str,
    slot_times: list[str],
    status: str = "AVAILABLE",
    location: GeoPoint | None = None,
) -> InspectorAvailability:
    return InspectorAvailability(
        employeeId=eid,
        availabilityStatus=status,
        slots=[Slot(slotTime=t, isAvailable=True) for t in slot_times],
        location=location,
    )


def test_solver_assigns_strict_preferred_time():
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)  # 10:00 AM IST
    req = make_req("r1", "560001", t)
    inspector = make_inspector("emp1", ["9:00 AM", "10:00 AM"])
    assigned, skipped = solve_bucket("560001", "2026-05-10", [req], [inspector])
    assert len(assigned) == 1
    assert assigned[0].employee_id == "emp1"
    assert assigned[0].slot_time == "10:00 AM"
    assert skipped == []


def test_solver_skips_when_no_slot_at_preferred_time():
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    req = make_req("r1", "560001", t)
    inspector = make_inspector("emp1", ["9:00 AM", "11:00 AM"])
    assigned, skipped = solve_bucket("560001", "2026-05-10", [req], [inspector])
    assert assigned == []
    assert len(skipped) == 1
    assert skipped[0].reason == "NO_SLOT_AT_PREFERRED_TIME"


def test_solver_skips_busy_inspectors():
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    req = make_req("r1", "560001", t)
    busy = make_inspector("busy", ["10:00 AM"], status="BUSY")
    free = make_inspector("free", ["10:00 AM"])
    assigned, _ = solve_bucket("560001", "2026-05-10", [req], [busy, free])
    assert len(assigned) == 1
    assert assigned[0].employee_id == "free"


def test_solver_does_not_double_book_same_inspector_slot():
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    r1 = make_req("r1", "560001", t)
    r2 = make_req("r2", "560001", t)
    inspector = make_inspector("emp1", ["10:00 AM"])
    assigned, skipped = solve_bucket("560001", "2026-05-10", [r1, r2], [inspector])
    assert len(assigned) == 1
    assert len(skipped) == 1
    assert skipped[0].reason == "SOLVER_CONTENTION"


def test_solver_finds_full_matching_when_supply_meets_demand():
    """Two requests at the same time, two inspectors each with that slot — both
    must be placed, on distinct inspectors. CP-SAT must not collapse them onto
    the same inspector even though the bucket has capacity.
    """
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)  # 10:00 AM IST
    r1 = make_req("r1", "560001", t)
    r2 = make_req("r2", "560001", t)
    inspector_a = make_inspector("A", ["10:00 AM"])
    inspector_b = make_inspector("B", ["10:00 AM"])

    assigned, skipped = solve_bucket(
        "560001", "2026-05-10", [r2, r1], [inspector_a, inspector_b]
    )
    assert len(assigned) == 2
    assert skipped == []
    assert {a.employee_id for a in assigned} == {"A", "B"}


def test_solver_uses_other_time_slots_when_one_inspector_full():
    """Different requests want different times; inspector A has both slots,
    inspector B has only one. Solver must place 3/3 by spreading across slots.
    """
    t10 = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)  # 10:00 AM IST
    t11 = datetime(2026, 5, 10, 5, 30, tzinfo=timezone.utc)  # 11:00 AM IST

    r1 = make_req("r1", "560001", t10)
    r2 = make_req("r2", "560001", t10)
    r3 = make_req("r3", "560001", t11)

    inspector_a = make_inspector("A", ["10:00 AM", "11:00 AM"])
    inspector_b = make_inspector("B", ["10:00 AM"])

    assigned, skipped = solve_bucket(
        "560001", "2026-05-10", [r1, r2, r3], [inspector_a, inspector_b]
    )
    assert len(assigned) == 3
    assert skipped == []


def test_solver_prefers_high_urgency_when_forced_to_choose():
    """Two requests, only one slot, different urgencies — urgent wins."""
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    low = make_req("r_low", "560001", t, urgency="LOW")
    urgent = make_req("r_urgent", "560001", t, urgency="URGENT")
    inspector = make_inspector("emp1", ["10:00 AM"])
    assigned, skipped = solve_bucket(
        "560001", "2026-05-10", [low, urgent], [inspector]
    )
    assert len(assigned) == 1
    assert assigned[0].request_id == "r_urgent"
    assert len(skipped) == 1
    assert skipped[0].request_id == "r_low"


def test_solver_handles_empty_input():
    assigned, skipped = solve_bucket("560001", "2026-05-10", [], [])
    assert assigned == []
    assert skipped == []


def test_solver_request_with_no_preferred_time_is_filtered_by_bucketing():
    """Defensive: if bucketing leaks a no-preferred-time request to the solver,
    it should still skip cleanly rather than crash.
    """
    req = make_req("r1", "560001", None)
    inspector = make_inspector("emp1", ["10:00 AM"])
    assigned, skipped = solve_bucket("560001", "2026-05-10", [req], [inspector])
    assert assigned == []
    assert skipped[0].reason == "NO_PREFERRED_TIME"


def test_solver_prefers_closer_inspector_when_distances_known():
    """Two inspectors with the same slot — solver picks the geographically
    closer one when both have location data."""
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)  # 10:00 AM IST
    req_loc = _point(12.9716, 77.5946)  # Bengaluru center
    near = _point(12.97, 77.60)  # ~1.7 km away
    far = _point(13.10, 77.70)  # ~17 km away

    req = make_req("r1", "560001", t, location=req_loc)
    inspector_near = make_inspector("near", ["10:00 AM"], location=near)
    inspector_far = make_inspector("far", ["10:00 AM"], location=far)

    # Order shouldn't matter — try both
    for inspectors in ([inspector_near, inspector_far], [inspector_far, inspector_near]):
        assigned, _ = solve_bucket("560001", "2026-05-10", [req], inspectors)
        assert len(assigned) == 1
        assert assigned[0].employee_id == "near", (
            f"expected closer inspector to win, got {assigned[0].employee_id}"
        )


def test_solver_distance_penalty_never_drops_assignment():
    """Even a very far inspector wins over no assignment."""
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    req_loc = _point(12.9716, 77.5946)  # Bengaluru
    very_far = _point(28.6139, 77.2090)  # Delhi (~1700 km)

    req = make_req("r1", "560001", t, location=req_loc)
    inspector = make_inspector("delhi", ["10:00 AM"], location=very_far)

    assigned, skipped = solve_bucket("560001", "2026-05-10", [req], [inspector])
    assert len(assigned) == 1
    assert assigned[0].employee_id == "delhi"
    assert skipped == []


def test_solver_missing_location_is_no_penalty_no_bonus():
    """If either side lacks location, no distance signal applies — solver
    chooses based on the other objective terms (or arbitrarily on ties).
    """
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    # Request has no location, two equal inspectors
    req = make_req("r1", "560001", t, location=None)
    a = make_inspector("A", ["10:00 AM"], location=_point(12.97, 77.59))
    b = make_inspector("B", ["10:00 AM"], location=None)
    assigned, _ = solve_bucket("560001", "2026-05-10", [req], [a, b])
    # Should pick exactly one; either is acceptable
    assert len(assigned) == 1
    assert assigned[0].employee_id in {"A", "B"}


def test_solver_urgency_dominates_distance():
    """A high-urgency request gets its preferred candidate even if distance
    favors using that candidate for a low-urgency request instead.
    """
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    # Single inspector slot — contention forces choice
    inspector_loc = _point(12.97, 77.60)
    inspector = make_inspector("only", ["10:00 AM"], location=inspector_loc)

    # Both requests want the same slot. The "low" request is closer; "urgent" is far.
    low = make_req("r_low", "560001", t, urgency="LOW", location=_point(12.97, 77.60))
    urgent = make_req("r_urgent", "560001", t, urgency="URGENT", location=_point(13.30, 77.90))

    assigned, skipped = solve_bucket("560001", "2026-05-10", [low, urgent], [inspector])
    assert len(assigned) == 1
    assert assigned[0].request_id == "r_urgent", (
        "urgency must dominate distance — W_urgency * URGENT > W_distance * km"
    )
