import logging
import time
import uuid

from app.clients.inspection_service import InspectionServiceClient
from app.core.bucketing import bucket_pending_requests, order_bucket_keys
from app.core.models import (
    Assignment,
    AutoAssignRequest,
    AutoAssignResponse,
    AutoAssignStats,
    SkippedRequest,
)
from app.core.picker import pick_assignments

logger = logging.getLogger(__name__)

ASSIGNED_BY = "AUTO_ASSIGNER"


async def run_auto_assign(
    client: InspectionServiceClient,
    request: AutoAssignRequest,
    default_dry_run: bool,
) -> AutoAssignResponse:
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    start = time.monotonic()
    dry_run = request.dry_run if request.dry_run is not None else default_dry_run

    logger.info("auto-assign run %s started (dry_run=%s)", run_id, dry_run)

    pending = await client.list_pending_requests()
    buckets = bucket_pending_requests(pending)

    if request.pincodes:
        allow = set(request.pincodes)
        buckets = {key: reqs for key, reqs in buckets.items() if key[0] in allow}

    ordered_keys = order_bucket_keys(buckets)

    all_assigned: list[Assignment] = []
    all_skipped: list[SkippedRequest] = []

    # Surface requests with no preferredTime up front (they never form a bucket).
    for r in pending:
        if not r.preferred_time:
            all_skipped.append(
                SkippedRequest(
                    request_id=r.request_id,
                    reason="NO_PREFERRED_TIME",
                    pincode=r.pincode,
                    date=None,
                )
            )

    for key in ordered_keys:
        bucket_reqs = buckets[(key.pincode, key.date)]
        try:
            inspectors = await client.get_inspector_availability(key.pincode, key.date)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "availability fetch failed for pincode=%s date=%s", key.pincode, key.date
            )
            for r in bucket_reqs:
                all_skipped.append(
                    SkippedRequest(
                        request_id=r.request_id,
                        reason=f"AVAILABILITY_FETCH_FAILED:{exc.__class__.__name__}",
                        pincode=key.pincode,
                        date=key.date,
                    )
                )
            continue

        assigned, skipped = pick_assignments(
            key.pincode, key.date, bucket_reqs, inspectors
        )
        all_assigned.extend(assigned)
        all_skipped.extend(skipped)

        if not dry_run:
            for a in assigned:
                try:
                    await client.assign(a.request_id, a.employee_id, ASSIGNED_BY)
                except Exception as exc:  # noqa: BLE001
                    logger.exception(
                        "assign failed for request=%s employee=%s",
                        a.request_id,
                        a.employee_id,
                    )
                    all_skipped.append(
                        SkippedRequest(
                            request_id=a.request_id,
                            reason=f"ASSIGN_CALL_FAILED:{exc.__class__.__name__}",
                            pincode=key.pincode,
                            date=key.date,
                        )
                    )

    elapsed_ms = int((time.monotonic() - start) * 1000)
    stats = AutoAssignStats(
        total_pending=len(pending),
        buckets=len(ordered_keys),
        assigned=len(all_assigned),
        skipped=len(all_skipped),
        elapsed_ms=elapsed_ms,
    )
    logger.info(
        "auto-assign run %s done: %d assigned, %d skipped in %dms",
        run_id,
        stats.assigned,
        stats.skipped,
        stats.elapsed_ms,
    )

    # If dry_run we did not call PUT /assign — the assigned list is the *plan*.
    return AutoAssignResponse(
        run_id=run_id,
        dry_run=dry_run,
        assigned=all_assigned,
        skipped=all_skipped,
        stats=stats,
    )
