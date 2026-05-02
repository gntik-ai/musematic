from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


async def test_tenant_admin_setup_token_validates_and_enforces_mfa_before_workspace(
    signup_default_e2e: None,
    platform_api_url: str,
    acme_tenant_host: str,
) -> None:
    del signup_default_e2e
    token = os.environ.get("SIGNUP_DEFAULT_E2E_SETUP_TOKEN")
    if not token:
        pytest.skip("SIGNUP_DEFAULT_E2E_SETUP_TOKEN is required for setup E2E")

    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        validate = await client.get(
            "/api/v1/setup/validate-token",
            headers={"Host": acme_tenant_host},
            params={"token": token},
        )
        assert validate.status_code == 200, validate.text
        assert validate.json()["current_step"] in {
            "tos",
            "credentials",
            "mfa",
            "workspace",
            "invitations",
            "done",
        }

        cookies = validate.cookies
        workspace = await client.post(
            "/api/v1/setup/step/workspace",
            headers={"Host": acme_tenant_host},
            cookies=cookies,
            json={"name": "Acme Research"},
        )
        assert workspace.status_code in {403, 422}, workspace.text
        assert "mfa" in workspace.text.lower() or "credentials" in workspace.text.lower()
