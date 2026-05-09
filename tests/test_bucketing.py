from datetime import datetime, timezone

from app.core.bucketing import (
    bucket_pending_requests,
    order_bucket_keys,
    urgency_weight,
)
from app.core.models import PendingRequest


def make_req(rid: str, pincode: str, time: datetime | None, urgency: str = "MEDIUM") -> PendingRequest:
    return PendingRequest(
        requestId=rid,
        pincode=pincode,
        preferredTime=time,
        urgencyLevel=urgency,
        status="insp-req-status01",
    )


def test_buckets_by_pincode_and_date():
    t1 = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)  # 10:00 AM IST
    t2 = datetime(2026, 5, 10, 5, 30, tzinfo=timezone.utc)  # 11:00 AM IST
    t3 = datetime(2026, 5, 11, 4, 30, tzinfo=timezone.utc)  # next day

    reqs = [
        make_req("r1", "560001", t1),
        make_req("r2", "560001", t2),
        make_req("r3", "560002", t1),
        make_req("r4", "560001", t3),
    ]
    buckets = bucket_pending_requests(reqs)
    assert set(buckets.keys()) == {
        ("560001", "2026-05-10"),
        ("560002", "2026-05-10"),
        ("560001", "2026-05-11"),
    }
    assert len(buckets[("560001", "2026-05-10")]) == 2


def test_requests_without_preferred_time_are_dropped():
    reqs = [make_req("r1", "560001", None)]
    assert bucket_pending_requests(reqs) == {}


def test_order_earliest_date_first_then_highest_demand():
    t_today = datetime(2026, 5, 10, 4, 30, tzinfo=timezone.utc)
    t_tomorrow = datetime(2026, 5, 11, 4, 30, tzinfo=timezone.utc)

    buckets = bucket_pending_requests(
        [
            make_req("r1", "560001", t_tomorrow, urgency="LOW"),
            make_req("r2", "560002", t_today, urgency="LOW"),
            make_req("r3", "560003", t_today, urgency="URGENT"),
            make_req("r4", "560003", t_today, urgency="URGENT"),
        ]
    )
    keys = order_bucket_keys(buckets)
    assert keys[0].date == "2026-05-10"
    # Among today's buckets, urgent demand wins.
    assert keys[0].pincode == "560003"
    assert keys[-1].date == "2026-05-11"


def test_urgency_weight_unknown_levels_default_to_one():
    assert urgency_weight(None) == 1
    assert urgency_weight("MYSTERY") == 1
    assert urgency_weight("urgent") == 100
