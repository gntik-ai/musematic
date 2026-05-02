from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]

PASSWORD = "TenantPass1!23"


async def test_cross_tenant_invitation_acceptance_creates_acme_scoped_identity(
    signup_default_e2e: None,
    platform_api_url: str,
    acme_tenant_host: str,
) -> None:
    del signup_default_e2e
    token = os.environ.get("SIGNUP_DEFAULT_E2E_INVITE_TOKEN")
    if not token:
        pytest.skip("SIGNUP_DEFAULT_E2E_INVITE_TOKEN is required for cross-tenant E2E")

    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        accepted = await client.post(
            f"/api/v1/accounts/invitations/{token}/accept",
            headers={"Host": acme_tenant_host},
            json={
                "token": token,
                "display_name": "Cross Tenant User",
                "password": PASSWORD,
            },
        )

    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["status"] == "active"
