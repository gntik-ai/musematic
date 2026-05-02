from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


async def test_onboarding_wizard_persists_dismisses_and_relaunches(
    signup_default_e2e: None,
    platform_api_url: str,
    default_tenant_host: str,
) -> None:
    del signup_default_e2e
    access_token = os.environ.get("SIGNUP_DEFAULT_E2E_DEFAULT_USER_TOKEN")
    if not access_token:
        pytest.skip("SIGNUP_DEFAULT_E2E_DEFAULT_USER_TOKEN is required for onboarding E2E")

    headers = {
        "Host": default_tenant_host,
        "Authorization": f"Bearer {access_token}",
    }
    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        state = await client.get("/api/v1/onboarding/state", headers=headers)
        assert state.status_code == 200, state.text

        dismiss = await client.post("/api/v1/onboarding/dismiss", headers=headers)
        assert dismiss.status_code == 200, dismiss.text
        assert dismiss.json()["dismissed_at"]

        relaunch = await client.post("/api/v1/onboarding/relaunch", headers=headers)
        assert relaunch.status_code == 200, relaunch.text
        assert relaunch.json()["dismissed_at"] is None
