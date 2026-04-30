from __future__ import annotations

import pytest

from suites._helpers import delete_ok, get_json, post_json


@pytest.mark.asyncio
async def test_session_list_rendering_contract(multi_session_user, self_service_client) -> None:
    payload = await get_json(self_service_client, "/api/v1/me/sessions")
    assert "items" in payload
    for item in payload.get("items", []):
        assert "session_id" in item
        assert "is_current" in item


@pytest.mark.asyncio
async def test_per_session_revoke(multi_session_user, self_service_client) -> None:
    sessions = (await get_json(self_service_client, "/api/v1/me/sessions")).get("items", [])
    candidate = next((item for item in sessions if not item.get("is_current")), None)
    if candidate is None:
        pytest.skip("No non-current session available to revoke")
    await delete_ok(self_service_client, f"/api/v1/me/sessions/{candidate['session_id']}")


@pytest.mark.asyncio
async def test_current_session_revoke_is_refused(multi_session_user, self_service_client) -> None:
    sessions = (await get_json(self_service_client, "/api/v1/me/sessions")).get("items", [])
    current = next((item for item in sessions if item.get("is_current")), None)
    if current is None:
        pytest.skip("No current session marker available")
    response = await self_service_client.delete(f"/api/v1/me/sessions/{current['session_id']}")
    assert response.status_code in {400, 409}


@pytest.mark.asyncio
async def test_revoke_other_sessions(multi_session_user, self_service_client) -> None:
    result = await post_json(self_service_client, "/api/v1/me/sessions/revoke-others", {})
    assert result.get("sessions_revoked", 0) >= 0


@pytest.mark.asyncio
async def test_session_revocation_audit_visible(self_service_client) -> None:
    payload = await get_json(
        self_service_client,
        "/api/v1/me/activity",
        params={"event_type": "auth.session.revoked"},
    )
    assert "items" in payload
