import httpx
import pytest
import respx

from app.clients.inspection_service import InspectionServiceClient
from app.core.models import AutoAssignRequest
from app.core.orchestrator import run_auto_assign


@pytest.mark.asyncio
@respx.mock
async def test_dry_run_returns_plan_without_calling_assign():
    base_url = "http://inspection-service.test"

    pending_route = respx.get(f"{base_url}/api/inspection-requests").mock(
        return_value=httpx.Response(
            200,
            json={
                "inspectionRequests": [
                    {
                        "requestId": "r1",
                        "pincode": "560001",
                        "preferredTime": "2026-05-10T04:30:00.000Z",  # 10:00 AM IST
                        "urgencyLevel": "MEDIUM",
                        "status": "insp-req-status01",
                    }
                ],
                "total": 1,
                "pageNumber": 1,
                "pageSize": 200,
                "totalPages": 1,
            },
        )
    )

    avail_route = respx.get(
        f"{base_url}/api/pincodes/560001/inspector-availability-statuses"
    ).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "employeeId": "emp1",
                    "availabilityStatus": "AVAILABLE",
                    "slots": [
                        {"slotTime": "10:00 AM", "isAvailable": True},
                        {"slotTime": "11:00 AM", "isAvailable": True},
                    ],
                    "hasEmptySlots": True,
                }
            ],
        )
    )

    assign_route = respx.put(
        f"{base_url}/api/internal/inspection-requests/r1/assign"
    ).mock(return_value=httpx.Response(200, json={}))

    async with InspectionServiceClient(base_url=base_url, api_key="k") as client:
        resp = await run_auto_assign(client, AutoAssignRequest(dry_run=True), default_dry_run=True)

    assert pending_route.called
    assert avail_route.called
    assert not assign_route.called  # dry run must not write
    assert resp.dry_run is True
    assert len(resp.assigned) == 1
    assert resp.assigned[0].request_id == "r1"
    assert resp.assigned[0].employee_id == "emp1"
    assert resp.assigned[0].slot_time == "10:00 AM"
    assert resp.stats.assigned == 1
    assert resp.stats.buckets == 1


@pytest.mark.asyncio
@respx.mock
async def test_apply_run_calls_assign_endpoint():
    base_url = "http://inspection-service.test"

    respx.get(f"{base_url}/api/inspection-requests").mock(
        return_value=httpx.Response(
            200,
            json={
                "inspectionRequests": [
                    {
                        "requestId": "r1",
                        "pincode": "560001",
                        "preferredTime": "2026-05-10T04:30:00.000Z",
                        "urgencyLevel": "MEDIUM",
                        "status": "insp-req-status01",
                    }
                ],
                "totalPages": 1,
            },
        )
    )
    respx.get(
        f"{base_url}/api/pincodes/560001/inspector-availability-statuses"
    ).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "employeeId": "emp1",
                    "availabilityStatus": "AVAILABLE",
                    "slots": [{"slotTime": "10:00 AM", "isAvailable": True}],
                }
            ],
        )
    )
    assign_route = respx.put(
        f"{base_url}/api/internal/inspection-requests/r1/assign"
    ).mock(return_value=httpx.Response(200, json={}))

    async with InspectionServiceClient(base_url=base_url, api_key="k") as client:
        resp = await run_auto_assign(
            client, AutoAssignRequest(dry_run=False), default_dry_run=True
        )

    assert assign_route.called
    body = assign_route.calls[0].request.read()
    assert b"emp1" in body
    assert b"AUTO_ASSIGNER" in body
    assert resp.dry_run is False
    assert resp.stats.assigned == 1


@pytest.mark.asyncio
@respx.mock
async def test_skipped_when_no_slot_at_preferred_time():
    base_url = "http://inspection-service.test"

    respx.get(f"{base_url}/api/inspection-requests").mock(
        return_value=httpx.Response(
            200,
            json={
                "inspectionRequests": [
                    {
                        "requestId": "r1",
                        "pincode": "560001",
                        "preferredTime": "2026-05-10T04:30:00.000Z",  # 10:00 AM IST
                        "urgencyLevel": "MEDIUM",
                        "status": "insp-req-status01",
                    }
                ],
                "totalPages": 1,
            },
        )
    )
    respx.get(
        f"{base_url}/api/pincodes/560001/inspector-availability-statuses"
    ).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "employeeId": "emp1",
                    "availabilityStatus": "AVAILABLE",
                    "slots": [{"slotTime": "11:00 AM", "isAvailable": True}],
                }
            ],
        )
    )

    async with InspectionServiceClient(base_url=base_url, api_key="k") as client:
        resp = await run_auto_assign(
            client, AutoAssignRequest(dry_run=True), default_dry_run=True
        )

    assert resp.assigned == []
    assert len(resp.skipped) == 1
    assert resp.skipped[0].reason == "NO_SLOT_AT_PREFERRED_TIME"
