from datetime import datetime, timezone

from app.core.models import InspectorAvailability, PendingRequest, Slot
from app.core.solver import solve_bucket


def make_req(rid: str, pincode: str, time: datetime | None, urgency: str = "MEDIUM") -> PendingRequest:
    return PendingRequest(
        requestId=rid,
        pincode=pincode,
        preferredTime=time,
        urgencyLevel=urgency,
        status="insp-req-status01",
    )


def make_inspector(eid: str, slot_times: list[str], status: str = "AVAILABLE") -> InspectorAvailability:
    return InspectorAvailability(
        employeeId=eid,
        availabilityStatus=status,
        slots=[Slot(slotTime=t, isAvailable=True) for t in slot_times],
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
