from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


def _require_tenant_e2e() -> None:
    if os.environ.get("RUN_TENANT_ARCHITECTURE_E2E") != "true":
        pytest.skip("set RUN_TENANT_ARCHITECTURE_E2E=true to run deletion e2e")


async def test_tenant_deletion_two_phase() -> None:
    _require_tenant_e2e()
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
        response = await client.post("/api/v1/_e2e/tenant-architecture/deletion-two-phase")
    assert response.status_code == 200, response.text
    assert response.json()["cascade_complete"] is True
