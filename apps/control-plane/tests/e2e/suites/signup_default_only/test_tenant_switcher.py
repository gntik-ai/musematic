from __future__ import annotations

import os
import time

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


async def test_tenant_switcher_memberships_payload_supports_fast_redirect_targets(
    signup_default_e2e: None,
    platform_api_url: str,
    default_tenant_host: str,
) -> None:
    del signup_default_e2e
    access_token = os.environ.get("SIGNUP_DEFAULT_E2E_MULTI_TENANT_USER_TOKEN")
    if not access_token:
        pytest.skip("SIGNUP_DEFAULT_E2E_MULTI_TENANT_USER_TOKEN is required for switcher E2E")

    started = time.perf_counter()
    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0) as client:
        memberships = await client.get(
            "/api/v1/me/memberships",
            headers={
                "Host": default_tenant_host,
                "Authorization": f"Bearer {access_token}",
            },
        )
    elapsed = time.perf_counter() - started

    assert memberships.status_code == 200, memberships.text
    payload = memberships.json()
    if payload["count"] < 2:
        pytest.skip("multi-tenant fixture is required for switcher redirect validation")
    assert elapsed < 3
    assert any(
        not item["is_current_tenant"] and item["login_url"]
        for item in payload["memberships"]
    )
