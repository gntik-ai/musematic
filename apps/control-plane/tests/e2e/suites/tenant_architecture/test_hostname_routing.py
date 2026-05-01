from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


def _require_tenant_e2e() -> None:
    if os.environ.get("RUN_TENANT_ARCHITECTURE_E2E") != "true":
        pytest.skip("set RUN_TENANT_ARCHITECTURE_E2E=true to run hostname routing e2e")


async def test_hostname_routing_patterns() -> None:
    _require_tenant_e2e()
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    hosts = [
        "app.localtest.me",
        "acme.localtest.me",
        "acme.api.localtest.me",
        "acme.grafana.localtest.me",
    ]
    async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
        responses = [
            await client.get("/api/v1/me/tenant", headers={"host": host}) for host in hosts
        ]
    assert all(response.status_code == 200 for response in responses), [
        response.text for response in responses
    ]
