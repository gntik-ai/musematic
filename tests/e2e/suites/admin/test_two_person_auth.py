from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_two_person_auth_request_and_self_approval_rejection(http_client_superadmin) -> None:
    create = await http_client_superadmin.post(
        "/api/v1/admin/2pa/requests",
        json={"action": "multi_region_ops.failover.execute", "payload": {"mode": "test"}},
    )
    assert create.status_code in {200, 201, 202}
    request_id = create.json().get("request_id") or create.json().get("id")

    if request_id:
        approve = await http_client_superadmin.post(f"/api/v1/admin/2pa/requests/{request_id}/approve")
        assert approve.status_code in {400, 403}
        assert "different" in approve.text.lower() or "initiator" in approve.text.lower()


@pytest.mark.asyncio
async def test_read_only_admin_cannot_initiate_two_person_auth(http_client) -> None:
    toggle = await http_client.patch(
        "/api/v1/admin/sessions/me/read-only-mode",
        json={"enabled": True},
    )
    assert toggle.status_code in {200, 204}

    try:
        response = await http_client.post(
            "/api/v1/admin/2pa/requests",
            json={"action": "multi_region_ops.failover.execute", "payload": {"mode": "test"}},
        )
        assert response.status_code in {403, 405}
    finally:
        reset = await http_client.patch(
            "/api/v1/admin/sessions/me/read-only-mode",
            json={"enabled": False},
        )
        assert reset.status_code in {200, 204}
