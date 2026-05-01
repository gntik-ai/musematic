from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


def _require_tenant_e2e() -> None:
    if os.environ.get("RUN_TENANT_ARCHITECTURE_E2E") != "true":
        pytest.skip("set RUN_TENANT_ARCHITECTURE_E2E=true to run unknown-subdomain e2e")


async def test_unknown_subdomain_404_is_opaque() -> None:
    _require_tenant_e2e()
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    async with httpx.AsyncClient(base_url=api_url, timeout=30.0) as client:
        responses = [
            await client.get(
                "/api/v1/me/tenant",
                headers={"host": f"unknown-{uuid4().hex}.localtest.me"},
            )
            for _ in range(10)
        ]
    assert {response.status_code for response in responses} == {404}
    assert len({hashlib.sha256(response.content).hexdigest() for response in responses}) == 1
