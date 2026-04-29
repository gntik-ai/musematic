from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_regular_admin_cannot_open_superadmin_tenant_api(http_client) -> None:
    response = await http_client.get("/api/v1/admin/tenants")
    assert response.status_code in {403, 404}
    if response.status_code == 403:
        payload = response.json()
        assert "superadmin" in str(payload).lower()


@pytest.mark.asyncio
async def test_regular_admin_user_list_is_tenant_scoped(http_client) -> None:
    response = await http_client.get("/api/v1/admin/users")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "tenant_id" in payload


@pytest.mark.asyncio
async def test_superadmin_can_open_admin_scoped_pages(http_client_superadmin) -> None:
    for path in ["/api/v1/admin/users", "/api/v1/admin/workspaces", "/api/v1/admin/tenants"]:
        response = await http_client_superadmin.get(path)
        assert response.status_code in {200, 404}
