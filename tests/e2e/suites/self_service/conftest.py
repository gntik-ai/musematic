from __future__ import annotations

from typing import Any

import pytest

from suites._helpers import assert_status, get_json, post_json


@pytest.fixture
async def self_service_client(http_client_workspace_member):
    return http_client_workspace_member


@pytest.fixture
async def clean_self_service_state(self_service_client):
    response = await self_service_client.post(
        "/api/v1/_e2e/reset",
        json={"scope": "self_service", "include_baseline": True},
    )
    if response.status_code not in {200, 202, 204, 404}:
        assert_status(response)
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
    response = await self_service_client.post(
        "/api/v1/_e2e/self-service/mfa",
        json={"enabled": True},
    )
    if response.status_code not in {200, 201, 202, 204, 404}:
        assert_status(response)
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
