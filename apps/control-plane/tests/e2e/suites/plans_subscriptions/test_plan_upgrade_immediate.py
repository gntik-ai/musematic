from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


async def test_plan_upgrade_immediate_journey() -> None:
    if os.environ.get("RUN_PLANS_SUBSCRIPTIONS_E2E") != "true":
        pytest.skip("set RUN_PLANS_SUBSCRIPTIONS_E2E=true to run upgrade e2e")
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    workspace_id = os.environ["PLANS_E2E_FREE_WORKSPACE_ID"]
    headers = {"Authorization": f"Bearer {os.environ['PLANS_E2E_WORKSPACE_ADMIN_TOKEN']}"}

    async with httpx.AsyncClient(base_url=api_url, headers=headers, timeout=30.0) as client:
        response = await client.post(
            f"/api/v1/workspaces/{workspace_id}/billing/upgrade",
            json={"target_plan_slug": "pro", "payment_method_token": "stub_pm_test"},
        )

    assert response.status_code in {200, 202}, response.text
    assert response.json()["subscription_after"]["plan_slug"] == "pro"
