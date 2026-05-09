from typing import Any

import httpx

from app.config import settings
from app.core.models import InspectorAvailability, PendingRequest


class InspectionServiceClient:
    """Thin httpx wrapper around the Inspection Service endpoints the optimizer uses.

    All calls attach the shared `X-API-KEY` header.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=(base_url or settings.inspection_service_url).rstrip("/"),
            headers={"X-API-KEY": api_key or settings.internal_api_key},
            timeout=timeout or settings.inspection_service_timeout_sec,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "InspectionServiceClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def list_pending_requests(
        self,
        page_size: int | None = None,
    ) -> list[PendingRequest]:
        """Page through `GET /api/inspection-requests?status=<PENDING>` until exhausted."""
        page_size = page_size or settings.inspection_service_page_size
        results: list[PendingRequest] = []
        page = 1
        while True:
            resp = await self._client.get(
                "/api/inspection-requests",
                params={
                    "status": settings.pending_status_id,
                    "pageNumber": page,
                    "pageSize": page_size,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            page_items = data.get("inspectionRequests", [])
            for item in page_items:
                results.append(PendingRequest.model_validate(item))
            total_pages = int(data.get("totalPages", 1))
            if page >= total_pages or not page_items:
                break
            page += 1
        return results

    async def get_inspector_availability(
        self, pincode: str, date: str
    ) -> list[InspectorAvailability]:
        """Hit `GET /api/pincodes/:pincode/inspector-availability-statuses?date=...`."""
        resp = await self._client.get(
            f"/api/pincodes/{pincode}/inspector-availability-statuses",
            params={"date": date},
        )
        resp.raise_for_status()
        data = resp.json()
        # The endpoint can return the array directly or wrapped — handle both.
        items = data if isinstance(data, list) else data.get("data", [])
        return [InspectorAvailability.model_validate(i) for i in items]

    async def assign(self, request_id: str, employee_id: str, assigned_by: str) -> None:
        """Apply an assignment via the internal endpoint."""
        resp = await self._client.put(
            f"/api/internal/inspection-requests/{request_id}/assign",
            json={"employeeId": employee_id, "assignedBy": assigned_by},
        )
        resp.raise_for_status()
