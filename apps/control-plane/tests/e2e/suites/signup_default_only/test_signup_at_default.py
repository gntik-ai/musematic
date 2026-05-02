from __future__ import annotations

import httpx
import pytest

from .conftest import unique_email

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]

PASSWORD = "SignupPass1!23"


async def test_default_tenant_signup_verifies_redirects_to_onboarding_and_has_workspace(
    signup_default_e2e: None,
    platform_api_url: str,
    default_tenant_host: str,
) -> None:
    del signup_default_e2e
    email = unique_email("upd048-default")
    headers = {"Host": default_tenant_host}

    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        register = await client.post(
            "/api/v1/accounts/register",
            headers=headers,
            json={
                "email": email,
                "display_name": "UPD048 Default User",
                "password": PASSWORD,
            },
        )
        assert register.status_code == 202, register.text

        token_response = await client.get(
            "/api/v1/_e2e/accounts/verification-token",
            headers=headers,
            params={"email": email},
        )
        if token_response.status_code == 404:
            pytest.skip("FEATURE_E2E_MODE is required for verification-token capture")
        assert token_response.status_code == 200, token_response.text

        verify = await client.post(
            "/api/v1/accounts/verify-email",
            headers=headers,
            json={"token": token_response.json()["token"]},
        )
        assert verify.status_code == 200, verify.text
        assert verify.json()["status"] == "active"

        login = await client.post(
            "/api/v1/auth/login",
            headers=headers,
            json={"email": email, "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        access_token = login.json()["access_token"]

        onboarding = await client.get(
            "/api/v1/onboarding/state",
            headers={**headers, "Authorization": f"Bearer {access_token}"},
        )
        assert onboarding.status_code == 200, onboarding.text
        payload = onboarding.json()
        assert payload["default_workspace_id"]
        assert payload["last_step_attempted"] in {
            "workspace_named",
            "invitations",
            "first_agent",
            "tour",
            "done",
        }
