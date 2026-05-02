from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


def _require_plans_e2e() -> None:
    if os.environ.get("RUN_PLANS_SUBSCRIPTIONS_E2E") != "true":
        pytest.skip("set RUN_PLANS_SUBSCRIPTIONS_E2E=true to run Journey J37")


async def test_free_hard_cap_journey_j37() -> None:
    _require_plans_e2e()
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    token = os.environ["PLANS_E2E_USER_TOKEN"]
    workspace_id = os.environ["PLANS_E2E_FREE_WORKSPACE_ID"]
    workflow_definition_id = os.environ["PLANS_E2E_WORKFLOW_DEFINITION_ID"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Host": os.environ.get("DEFAULT_TENANT_HOST", "app.localhost"),
    }
    payload = {
        "workflow_definition_id": workflow_definition_id,
        "workspace_id": workspace_id,
        "input_parameters": {},
    }

    async with httpx.AsyncClient(base_url=api_url, timeout=30.0, headers=headers) as client:
        for _ in range(100):
            response = await client.post("/api/v1/executions", json=payload)
            assert response.status_code in {200, 201, 202}, response.text

        capped = await client.post("/api/v1/executions", json=payload)

    assert capped.status_code == 402, capped.text
    body = capped.json()
    assert body["code"] == "quota_exceeded"
    assert body["details"]["quota_name"] == "executions_per_month"
    assert body["details"]["upgrade_url"] == f"/workspaces/{workspace_id}/billing/upgrade"
