from collections import defaultdict
from datetime import timezone
from typing import Iterable

from app.core.models import BucketKey, PendingRequest


URGENCY_WEIGHTS: dict[str, int] = {
    "URGENT": 100,
    "HIGH": 50,
    "MEDIUM": 10,
    "LOW": 1,
}


def urgency_weight(level: str | None) -> int:
    if not level:
        return 1
    return URGENCY_WEIGHTS.get(level.upper(), 1)


def bucket_pending_requests(
    requests: Iterable[PendingRequest],
) -> dict[tuple[str, str], list[PendingRequest]]:
    """Group requests by (pincode, YYYY-MM-DD of preferredTime).

    Requests with no preferredTime are skipped — strict mode requires a target slot.
    """
    buckets: dict[tuple[str, str], list[PendingRequest]] = defaultdict(list)
    for req in requests:
        if not req.preferred_time:
            continue
        date_str = req.preferred_time.astimezone(timezone.utc).date().isoformat()
        buckets[(req.pincode, date_str)].append(req)
    return buckets


def order_bucket_keys(
    buckets: dict[tuple[str, str], list[PendingRequest]],
) -> list[BucketKey]:
    """Order buckets so shared inspectors are consumed sensibly:

    1. Earliest date first
    2. Within a date, highest urgency-weighted demand first
    """

    def sort_key(item: tuple[tuple[str, str], list[PendingRequest]]) -> tuple[str, int]:
        (_, date_str), reqs = item
        demand = sum(urgency_weight(r.urgency_level) for r in reqs)
        return (date_str, -demand)

    ordered = sorted(buckets.items(), key=sort_key)
    return [BucketKey(pincode=pin, date=date) for (pin, date), _ in ordered]
