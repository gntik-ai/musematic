from __future__ import annotations

from decimal import Decimal
from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.billing.quotas.overage import OverageService
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription, insert_usage_record

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_overage_cap_reached_blocks_more_overage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(
            session,
            plan_slug="pro",
            minutes=Decimal("2400"),
        )
        await OverageService(session=session).authorize(
            fixture.workspace_id,
            fixture.period_start,
            Decimal("50"),
            fixture.owner_id,
        )
        await insert_usage_record(
            session,
            tenant_id=fixture.tenant_id,
            workspace_id=fixture.workspace_id,
            subscription_id=fixture.subscription_id,
            period_start=fixture.period_start,
            period_end=fixture.period_end,
            metric="minutes",
            quantity=Decimal("500"),
            is_overage=True,
        )

        result = await QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
        ).check_execution(fixture.workspace_id)

        assert result.decision == "OVERAGE_CAP_EXCEEDED"
        assert result.quota_name == "minutes_per_month"
        assert result.limit == Decimal("50")

        await session.rollback()
