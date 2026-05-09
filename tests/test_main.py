import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import app


def test_healthz_is_unauthenticated():
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_auto_assign_requires_api_key():
    client = TestClient(app)
    resp = client.post("/auto-assign", json={})
    assert resp.status_code == 401


def test_auto_assign_rejects_wrong_api_key():
    client = TestClient(app)
    resp = client.post("/auto-assign", json={}, headers={"X-API-KEY": "wrong"})
    assert resp.status_code == 401


@respx.mock
def test_auto_assign_with_valid_key_runs():
    respx.get("http://inspection-service.test/api/inspection-requests").mock(
        return_value=httpx.Response(
            200,
            json={"inspectionRequests": [], "totalPages": 1},
        )
    )

    client = TestClient(app)
    resp = client.post(
        "/auto-assign",
        json={"dry_run": True},
        headers={"X-API-KEY": "test-key"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["dry_run"] is True
    assert body["stats"]["total_pending"] == 0
