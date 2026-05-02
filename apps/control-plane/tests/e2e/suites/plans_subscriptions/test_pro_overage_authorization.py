from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


def _require_plans_e2e() -> None:
    if os.environ.get("RUN_PLANS_SUBSCRIPTIONS_E2E") != "true":
        pytest.skip("set RUN_PLANS_SUBSCRIPTIONS_E2E=true to run Pro overage e2e")


async def test_pro_overage_authorization_journey() -> None:
    _require_plans_e2e()
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    token = os.environ["PLANS_E2E_WORKSPACE_ADMIN_TOKEN"]
    workspace_id = os.environ["PLANS_E2E_PRO_WORKSPACE_ID"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Host": os.environ.get("DEFAULT_TENANT_HOST", "app.localhost"),
    }

    async with httpx.AsyncClient(base_url=api_url, timeout=30.0, headers=headers) as client:
        state = await client.get(f"/api/v1/workspaces/{workspace_id}/billing/overage-authorization")
        assert state.status_code == 200, state.text
        authorized = await client.post(
            f"/api/v1/workspaces/{workspace_id}/billing/overage-authorization",
            json={"max_overage_eur": "50.00"},
        )
        assert authorized.status_code in {200, 201}, authorized.text
        summary = await client.get(f"/api/v1/workspaces/{workspace_id}/billing")

    assert summary.status_code == 200, summary.text
    assert summary.json()["overage"]["is_authorized"] is True
