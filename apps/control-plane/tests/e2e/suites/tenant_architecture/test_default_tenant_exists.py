from __future__ import annotations

import os
from uuid import UUID

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]

DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _require_tenant_e2e() -> None:
    if os.environ.get("RUN_TENANT_ARCHITECTURE_E2E") != "true":
        pytest.skip("set RUN_TENANT_ARCHITECTURE_E2E=true to validate default tenant")


async def test_default_tenant_exists_after_install() -> None:
    _require_tenant_e2e()
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
        response = await client.get("/api/v1/me/tenant", headers={"host": "app.localtest.me"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert UUID(payload["id"]) == DEFAULT_TENANT_ID
    assert payload["slug"] == "default"
    assert payload["subdomain"] == "app"
