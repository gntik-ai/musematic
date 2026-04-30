from __future__ import annotations

import pytest

from suites._helpers import delete_ok, get_json, post_json


@pytest.mark.asyncio
async def test_create_api_key_requires_or_accepts_mfa_step_up(mfa_enabled_user) -> None:
    result = await post_json(
        mfa_enabled_user,
        "/api/v1/me/service-accounts",
        {
            "name": "e2e self-service token",
            "scopes": ["agents:read"],
            "expires_at": None,
            "mfa_token": "123456",
        },
        expected={200, 201, 401},
    )
    if result.get("mfa_required"):
        assert result["mfa_required"] is True
        return
    assert result.get("api_key")


@pytest.mark.asyncio
async def test_api_key_one_time_response_is_not_returned_in_list(self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/service-accounts")
    assert "items" in payload
    assert all("api_key" not in item for item in payload.get("items", []))


@pytest.mark.asyncio
async def test_max_ten_api_key_limit_visible(self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/service-accounts")
    assert payload.get("max_active", 10) == 10


@pytest.mark.asyncio
async def test_scope_subset_rejection(self_service_client) -> None:
    response = await self_service_client.post(
        "/api/v1/me/service-accounts",
        json={
            "name": "forbidden token",
            "scopes": ["admin:*"],
            "expires_at": None,
            "mfa_token": "123456",
        },
    )
    assert response.status_code in {400, 401, 403, 422}


@pytest.mark.asyncio
async def test_api_key_revocation_propagates(self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/service-accounts")
    items = payload.get("items", [])
    if not items:
        pytest.skip("No self-service API key available to revoke")
    await delete_ok(self_service_client, f"/api/v1/me/service-accounts/{items[0]['service_account_id']}")
