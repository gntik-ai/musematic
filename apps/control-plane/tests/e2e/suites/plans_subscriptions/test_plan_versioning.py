from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.e2e, pytest.mark.asyncio]


def _require_plans_e2e() -> None:
    if os.environ.get("RUN_PLANS_SUBSCRIPTIONS_E2E") != "true":
        pytest.skip("set RUN_PLANS_SUBSCRIPTIONS_E2E=true to run plans/subscriptions Journey J30")


async def test_plan_versioning_journey_j30() -> None:
    _require_plans_e2e()
    api_url = os.environ.get("PLATFORM_API_URL", "http://localhost:8081")
    token = os.environ["PLANS_E2E_SUPERADMIN_TOKEN"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Host": os.environ.get("DEFAULT_TENANT_HOST", "app.localhost"),
    }
    payload = {
        "price_monthly": "59.00",
        "executions_per_day": 500,
        "executions_per_month": 5000,
        "minutes_per_day": 240,
        "minutes_per_month": 2400,
        "max_workspaces": 5,
        "max_agents_per_workspace": 50,
        "max_users_per_workspace": 25,
        "overage_price_per_minute": "0.1000",
        "trial_days": 14,
        "quota_period_anchor": "subscription_anniversary",
        "extras": {},
    }

    async with httpx.AsyncClient(base_url=api_url, timeout=30.0, headers=headers) as client:
        publish = await client.post("/api/v1/admin/plans/pro/versions", json=payload)
        assert publish.status_code == 201, publish.text
        new_version = publish.json()["version"]

        history = await client.get("/api/v1/admin/plans/pro/versions")
        assert history.status_code == 200, history.text
        versions = history.json()["items"]

    assert any(item["version"] == new_version for item in versions)
    prior = next(item for item in versions if item["version"] == new_version - 1)
    assert prior["deprecated_at"] is not None
    assert versions[0]["diff_against_prior"]["price_monthly"]["to"] == "59.00"
