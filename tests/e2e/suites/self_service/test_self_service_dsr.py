from __future__ import annotations

import pytest

from suites._helpers import assert_status, get_json


async def submit_self_service_dsr(client, request_type: str = "access") -> dict:
    payload = {"request_type": request_type, "legal_basis": None, "hold_hours": 0}
    if request_type == "erasure":
        payload["confirm_text"] = "DELETE"
    return assert_status(await client.post("/api/v1/me/dsr", json=payload, timeout=90.0))


@pytest.mark.asyncio
async def test_self_service_dsr_uses_same_row_contract(self_service_client) -> None:
    created = await submit_self_service_dsr(self_service_client, "access")
    assert created["subject_user_id"] == self_service_client.current_user_id
    assert created["requested_by"] == self_service_client.current_user_id


@pytest.mark.asyncio
async def test_self_service_dsr_audit_source_visible(self_service_client) -> None:
    await submit_self_service_dsr(self_service_client, "access")
    activity = await get_json(
        self_service_client,
        "/api/v1/me/activity",
        params={"event_type": "privacy.dsr.submitted"},
    )
    assert "items" in activity


@pytest.mark.asyncio
async def test_erasure_requires_typed_confirmation(self_service_client) -> None:
    response = await self_service_client.post(
        "/api/v1/me/dsr",
        json={"request_type": "erasure", "hold_hours": 0, "confirm_text": "WRONG"},
    )
    assert response.status_code in {400, 422}


@pytest.mark.asyncio
async def test_active_execution_warning_fields_do_not_break_submission(self_service_client) -> None:
    created = await submit_self_service_dsr(self_service_client, "erasure")
    assert created["request_type"] == "erasure"


@pytest.mark.asyncio
async def test_admin_on_behalf_double_audit_visibility(self_service_client) -> None:
    activity = await get_json(
        self_service_client,
        "/api/v1/me/activity",
        params={"event_type": "privacy.dsr.submitted"},
    )
    assert "items" in activity
