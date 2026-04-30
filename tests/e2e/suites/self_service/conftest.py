from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pyotp
import pytest

from fixtures.http_client import AuthenticatedAsyncClient
from suites._helpers import assert_status, get_json, post_json

SELF_SERVICE_PASSWORD = "e2e-test-password"


@pytest.fixture
async def self_service_client(
    platform_api_url: str,
    http_client_superadmin,
) -> AsyncIterator[AuthenticatedAsyncClient]:
    user_id = uuid4()
    email = f"self-service-{user_id.hex}@e2e.test"
    provisioned = await http_client_superadmin.post(
        "/api/v1/_e2e/users",
        json={
            "id": str(user_id),
            "email": email,
            "password": SELF_SERVICE_PASSWORD,
            "display_name": "E2E Self-Service User",
            "status": "active",
            "roles": ["workspace_member"],
        },
    )
    assert_status(provisioned)
    async with AuthenticatedAsyncClient(platform_api_url) as client:
        await client.login_as(email, SELF_SERVICE_PASSWORD)
        yield client


@pytest.fixture
async def clean_self_service_state():
    yield


@pytest.fixture
async def logged_in_user_with_alerts(self_service_client, clean_self_service_state) -> dict[str, Any]:
    response = await self_service_client.post(
        "/api/v1/_e2e/self-service/alerts",
        json={"count": 15},
    )
    if response.status_code in {200, 201, 202}:
        return response.json()
    alerts = await get_json(self_service_client, "/api/v1/me/alerts", params={"limit": 15})
    return {"items": alerts.get("items", [])}


@pytest.fixture
async def mfa_enabled_user(self_service_client, clean_self_service_state):
    enrollment = assert_status(await self_service_client.post("/api/v1/auth/mfa/enroll", json={}))
    secret = str(enrollment.get("secret") or enrollment.get("secret_key") or "")
    code = pyotp.TOTP(secret.replace(" ", "")).now()
    assert_status(
        await self_service_client.post(
            "/api/v1/auth/mfa/confirm",
            json={"totp_code": code},
        )
    )
    return self_service_client


@pytest.fixture
async def multi_session_user(self_service_client, clean_self_service_state) -> dict[str, Any]:
    response = await self_service_client.post(
        "/api/v1/_e2e/self-service/sessions",
        json={"count": 3},
    )
    if response.status_code in {200, 201, 202}:
        return response.json()
    sessions = await get_json(self_service_client, "/api/v1/me/sessions")
    return {"items": sessions.get("items", [])}


@pytest.fixture
async def consented_user(self_service_client, clean_self_service_state) -> dict[str, Any]:
    response = await self_service_client.post(
        "/api/v1/_e2e/self-service/consents",
        json={"consents": ["ai_interaction", "data_collection", "training_use"]},
    )
    if response.status_code in {200, 201, 202}:
        return response.json()
    consents = await get_json(self_service_client, "/api/v1/me/consent")
    return {"items": consents.get("items", [])}


async def current_audit_count(client, event_type: str) -> int:
    payload = await get_json(client, "/api/v1/me/activity", params={"event_type": event_type})
    return len(payload.get("items", []))


async def submit_self_service_dsr(client, request_type: str = "access") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_type": request_type,
        "legal_basis": None,
        "hold_hours": 0,
    }
    if request_type == "erasure":
        payload["confirm_text"] = "DELETE"
    return await post_json(client, "/api/v1/me/dsr", payload)
