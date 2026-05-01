from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


def _require_tenant_e2e() -> None:
    if os.environ.get("RUN_TENANT_ARCHITECTURE_E2E") != "true":
        pytest.skip("set RUN_TENANT_ARCHITECTURE_E2E=true to run Journey J31")


async def test_j31_cross_tenant_isolation_matrix() -> None:
    _require_tenant_e2e()
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
        response = await client.get(
            "/api/v1/_e2e/tenant-architecture/cross-tenant-isolation"
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["resource_types_checked"] >= 8
    assert payload["opaque_404_byte_identity"] is True
