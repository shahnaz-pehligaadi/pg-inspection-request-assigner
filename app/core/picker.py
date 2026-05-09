"""Phase 1 placeholder picker.

Greedy assignment with strict preferredTime: for each request, pick the first
inspector that has an AVAILABLE slot exactly matching the request's preferred time.
Will be replaced by the OR-Tools CP-SAT solver in Phase 2.
"""
from datetime import timezone

from app.core.models import (
    Assignment,
    InspectorAvailability,
    PendingRequest,
    SkippedRequest,
)


def _format_preferred_time(req: PendingRequest) -> str | None:
    """Format the request's preferredTime into the slotTime shape used by the
    availability API (e.g. "9:00 AM", "10:30 AM").

    The availability API formats slot times in IST. preferredTime in DB is UTC.
    """
    if not req.preferred_time:
        return None
    # preferredTime is stored in UTC; the inspection availability API renders slot
    # labels in IST. Convert here so we compare like-for-like.
    ist = req.preferred_time.astimezone(timezone.utc)
    # +5:30
    ist_hour = (ist.hour + 5) % 24
    ist_minute = ist.minute + 30
    if ist_minute >= 60:
        ist_minute -= 60
        ist_hour = (ist_hour + 1) % 24

    suffix = "AM" if ist_hour < 12 else "PM"
    display_hour = ist_hour % 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{ist_minute:02d} {suffix}"


def pick_assignments(
    pincode: str,
    date: str,
    requests: list[PendingRequest],
    inspectors: list[InspectorAvailability],
) -> tuple[list[Assignment], list[SkippedRequest]]:
    """Greedy first-fit picker. Returns (assignments, skipped)."""
    assignments: list[Assignment] = []
    skipped: list[SkippedRequest] = []

    # Track per-inspector consumed slot times within this run.
    consumed: dict[str, set[str]] = {i.employee_id: set() for i in inspectors}

    for req in requests:
        wanted = _format_preferred_time(req)
        if not wanted:
            skipped.append(
                SkippedRequest(
                    request_id=req.request_id,
                    reason="NO_PREFERRED_TIME",
                    pincode=pincode,
                    date=date,
                )
            )
            continue

        picked = False
        for ins in inspectors:
            if ins.availability_status != "AVAILABLE":
                continue
            if wanted in consumed[ins.employee_id]:
                continue
            for slot in ins.slots:
                if slot.is_available and slot.slot_time == wanted:
                    assignments.append(
                        Assignment(
                            request_id=req.request_id,
                            employee_id=ins.employee_id,
                            slot_time=slot.slot_time,
                            pincode=pincode,
                            date=date,
                        )
                    )
                    consumed[ins.employee_id].add(slot.slot_time)
                    picked = True
                    break
            if picked:
                break

        if not picked:
            skipped.append(
                SkippedRequest(
                    request_id=req.request_id,
                    reason="NO_SLOT_AT_PREFERRED_TIME",
                    pincode=pincode,
                    date=date,
                )
            )

    return assignments, skipped
