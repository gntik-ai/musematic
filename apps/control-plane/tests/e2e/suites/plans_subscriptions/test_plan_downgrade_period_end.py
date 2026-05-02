from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


async def test_plan_downgrade_period_end_journey() -> None:
    if os.environ.get("RUN_PLANS_SUBSCRIPTIONS_E2E") != "true":
        pytest.skip("set RUN_PLANS_SUBSCRIPTIONS_E2E=true to run downgrade e2e")
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    workspace_id = os.environ["PLANS_E2E_PRO_WORKSPACE_ID"]
    headers = {"Authorization": f"Bearer {os.environ['PLANS_E2E_WORKSPACE_ADMIN_TOKEN']}"}

    async with httpx.AsyncClient(base_url=api_url, headers=headers, timeout=30.0) as client:
        response = await client.post(
            f"/api/v1/workspaces/{workspace_id}/billing/downgrade",
            json={"target_plan_slug": "free"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["cancel_at_period_end"] is True
