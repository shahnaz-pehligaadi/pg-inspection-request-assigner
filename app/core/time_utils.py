"""Time helpers shared by the solver and (legacy) picker."""
from datetime import timezone

from app.core.models import PendingRequest


def format_preferred_time_to_ist_slot(req: PendingRequest) -> str | None:
    """Render a request's preferredTime in the slotTime shape used by the
    Inspection Service availability API (e.g. "9:00 AM", "10:30 AM").

    The DB stores preferredTime as UTC; the availability API renders slot
    labels in IST. Convert here so we compare like-for-like.
    """
    if not req.preferred_time:
        return None
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
