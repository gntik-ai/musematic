from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.billing.quotas.overage import OverageService
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import (
    create_workspace_subscription,
    insert_usage_record,
    set_subscription_period,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_overage_authorization_expires_at_next_period(
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
        old_period_result = await QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
        ).check_execution(fixture.workspace_id)
        new_start = fixture.period_end
        new_end = new_start + timedelta(days=30)
        await set_subscription_period(
            session,
            subscription_id=fixture.subscription_id,
            period_start=new_start,
            period_end=new_end,
        )
        await insert_usage_record(
            session,
            tenant_id=fixture.tenant_id,
            workspace_id=fixture.workspace_id,
            subscription_id=fixture.subscription_id,
            period_start=new_start,
            period_end=new_end,
            metric="minutes",
            quantity=Decimal("2400"),
        )

        new_period_result = await QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
        ).check_execution(fixture.workspace_id)

        assert old_period_result.decision == "OVERAGE_AUTHORIZED"
        assert new_period_result.decision == "OVERAGE_REQUIRED"

        await session.rollback()
