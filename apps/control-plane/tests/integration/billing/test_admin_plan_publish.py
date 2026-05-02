from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_admin_publish_plan_version_records_side_effects(
    billing_admin_client,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    response = await billing_admin_client.client.post(
        "/api/v1/admin/plans/pro/versions",
        json=_pro_payload("59.00"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["version"] == 2
    assert body["diff_against_prior"]["price_monthly"] == {"from": "49.00", "to": "59.00"}

    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT pv.version, pv.price_monthly, pv.deprecated_at
                      FROM plan_versions pv
                      JOIN plans p ON p.id = pv.plan_id
                     WHERE p.slug = 'pro'
                     ORDER BY pv.version
                    """
                )
            )
        ).mappings().all()
        assert [row["version"] for row in rows] == [1, 2]
        assert rows[0]["deprecated_at"] is not None
        assert Decimal(rows[1]["price_monthly"]) == Decimal("59.00")

        audit_payload = await session.scalar(
            text(
                """
                SELECT canonical_payload
                  FROM audit_chain_entries
                 WHERE event_type = 'billing.plan.published'
                 ORDER BY sequence_number DESC
                 LIMIT 1
                """
            )
        )
        assert audit_payload["plan_slug"] == "pro"
        assert audit_payload["diff"]["price_monthly"] == {"from": "49.00", "to": "59.00"}

    assert billing_admin_client.producer.calls
    event_args = billing_admin_client.producer.calls[-1]["args"]
    assert event_args[0] == "billing.lifecycle"
    assert event_args[2] == "billing.plan.published"
    assert event_args[3]["plan_slug"] == "pro"


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
