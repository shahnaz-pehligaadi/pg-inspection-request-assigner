from datetime import datetime, timezone

from app.core.models import InspectorAvailability, PendingRequest, Slot
from app.core.picker import _format_preferred_time, pick_assignments


def make_req(rid: str, pincode: str, time: datetime | None) -> PendingRequest:
    return PendingRequest(
        requestId=rid,
        pincode=pincode,
        preferredTime=time,
        urgencyLevel="MEDIUM",
        status="insp-req-status01",
    )


def make_inspector(eid: str, slot_times: list[str], status: str = "AVAILABLE") -> InspectorAvailability:
    return InspectorAvailability(
        employeeId=eid,
        availabilityStatus=status,
        slots=[Slot(slotTime=t, isAvailable=True) for t in slot_times],
    )


def test_format_preferred_time_utc_to_ist():
    # 04:30 UTC => 10:00 AM IST
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    assert _format_preferred_time(make_req("r", "p", t)) == "10:00 AM"


def test_format_preferred_time_handles_pm():
    # 09:30 UTC => 3:00 PM IST
    t = datetime(2026, 5, 10, 9, 30, tzinfo=timezone.utc)
    assert _format_preferred_time(make_req("r", "p", t)) == "3:00 PM"


def test_format_preferred_time_handles_minute_carry():
    # 03:31 UTC => 9:01 AM IST  (31 + 30 = 61 -> minute 01, hour +1)
    t = datetime(2026, 5, 10, 3, 31, tzinfo=timezone.utc)
    assert _format_preferred_time(make_req("r", "p", t)) == "9:01 AM"


def test_picker_assigns_strict_preferred_time():
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)  # 10:00 AM IST
    req = make_req("r1", "560001", t)
    inspector = make_inspector("emp1", ["9:00 AM", "10:00 AM"])
    assigned, skipped = pick_assignments("560001", "2026-05-10", [req], [inspector])
    assert len(assigned) == 1
    assert assigned[0].employee_id == "emp1"
    assert assigned[0].slot_time == "10:00 AM"
    assert skipped == []


def test_picker_skips_when_no_slot_at_preferred_time():
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    req = make_req("r1", "560001", t)
    inspector = make_inspector("emp1", ["9:00 AM", "11:00 AM"])
    assigned, skipped = pick_assignments("560001", "2026-05-10", [req], [inspector])
    assert assigned == []
    assert len(skipped) == 1
    assert skipped[0].reason == "NO_SLOT_AT_PREFERRED_TIME"


def test_picker_skips_busy_inspectors():
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    req = make_req("r1", "560001", t)
    busy = make_inspector("busy", ["10:00 AM"], status="BUSY")
    free = make_inspector("free", ["10:00 AM"])
    assigned, _ = pick_assignments("560001", "2026-05-10", [req], [busy, free])
    assert len(assigned) == 1
    assert assigned[0].employee_id == "free"


def test_picker_does_not_double_book_same_inspector_slot():
    t = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    r1 = make_req("r1", "560001", t)
    r2 = make_req("r2", "560001", t)
    inspector = make_inspector("emp1", ["10:00 AM"])
    assigned, skipped = pick_assignments("560001", "2026-05-10", [r1, r2], [inspector])
    assert len(assigned) == 1
    assert assigned[0].request_id == "r1"
    assert len(skipped) == 1
    assert skipped[0].request_id == "r2"


def test_picker_skips_request_with_no_preferred_time():
    req = make_req("r1", "560001", None)
    inspector = make_inspector("emp1", ["10:00 AM"])
    assigned, skipped = pick_assignments("560001", "2026-05-10", [req], [inspector])
    assert assigned == []
    assert skipped[0].reason == "NO_PREFERRED_TIME"
