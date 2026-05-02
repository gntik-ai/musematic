from __future__ import annotations

import hashlib
from uuid import uuid4

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


async def test_enterprise_and_unknown_signup_surfaces_are_byte_identical_404s(
    signup_default_e2e: None,
    platform_api_url: str,
    acme_tenant_host: str,
) -> None:
    del signup_default_e2e
    hosts = [acme_tenant_host, f"bogus-{uuid4().hex[:8]}.localhost"]

    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        responses = [
            await client.post(
                "/api/v1/accounts/register",
                headers={"Host": host},
                json={
                    "email": "probe@example.test",
                    "display_name": "Probe",
                    "password": "ProbePass1!23",
                },
            )
            for host in hosts
        ]

    assert {response.status_code for response in responses} == {404}
    assert len({hashlib.sha256(response.content).hexdigest() for response in responses}) == 1
