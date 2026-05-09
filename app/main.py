import logging

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.clients.inspection_service import InspectionServiceClient
from app.config import settings
from app.core.models import AutoAssignRequest, AutoAssignResponse
from app.core.orchestrator import run_auto_assign

logging.basicConfig(level=settings.log_level)

app = FastAPI(title="pg-assignment-optimizer", version="0.1.0")


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-KEY")) -> None:
    if not x_api_key or x_api_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-KEY"
        )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


@app.post(
    "/auto-assign",
    response_model=AutoAssignResponse,
    dependencies=[Depends(require_api_key)],
)
async def auto_assign(payload: AutoAssignRequest | None = None) -> AutoAssignResponse:
    payload = payload or AutoAssignRequest()
    async with InspectionServiceClient() as client:
        return await run_auto_assign(client, payload, settings.default_dry_run)
