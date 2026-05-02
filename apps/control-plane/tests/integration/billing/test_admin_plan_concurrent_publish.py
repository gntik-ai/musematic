from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_admin_publish_returns_conflict_when_plan_lock_is_held(
    billing_admin_client,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        plan_id = await session.scalar(text("SELECT id FROM plans WHERE slug = 'pro'"))
        assert plan_id is not None
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:plan_id)::bigint)"),
            {"plan_id": str(plan_id)},
        )

        response = await billing_admin_client.client.post(
            "/api/v1/admin/plans/pro/versions",
            json=_pro_payload("59.00"),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "BILLING_PLAN_VERSION_IN_PROGRESS"
        await session.rollback()


def _pro_payload(price: str) -> dict[str, object]:
    return {
        "price_monthly": price,
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
