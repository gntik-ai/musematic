from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


def _require_plans_e2e() -> None:
    if os.environ.get("RUN_PLANS_SUBSCRIPTIONS_E2E") != "true":
        pytest.skip("set RUN_PLANS_SUBSCRIPTIONS_E2E=true to run Enterprise unlimited e2e")


async def test_enterprise_unlimited_journey() -> None:
    _require_plans_e2e()
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    token = os.environ["PLANS_E2E_ENTERPRISE_TOKEN"]
    workspace_id = os.environ["PLANS_E2E_ENTERPRISE_WORKSPACE_ID"]
    workflow_definition_id = os.environ["PLANS_E2E_WORKFLOW_DEFINITION_ID"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Host": os.environ["PLANS_E2E_ENTERPRISE_HOST"],
    }
    payload = {
        "workflow_definition_id": workflow_definition_id,
        "workspace_id": workspace_id,
        "input_parameters": {},
    }

    async with httpx.AsyncClient(base_url=api_url, timeout=30.0, headers=headers) as client:
        responses = [
            await client.post("/api/v1/executions", json=payload)
            for _ in range(100)
        ]

    assert all(response.status_code in {200, 201, 202} for response in responses)
