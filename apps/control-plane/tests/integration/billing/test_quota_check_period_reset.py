from __future__ import annotations

from datetime import timedelta
from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription, set_subscription_period

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_execution_counter_resets_when_subscription_period_advances(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session, executions=100)
        blocked = await QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
        ).check_execution(fixture.workspace_id)
        new_start = fixture.period_end
        new_end = new_start + timedelta(days=31)

        await set_subscription_period(
            session,
            subscription_id=fixture.subscription_id,
            period_start=new_start,
            period_end=new_end,
        )

        allowed = await QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
        ).check_execution(fixture.workspace_id)

        assert blocked.decision == "HARD_CAP_EXCEEDED"
        assert allowed.decision == "OK"

        await session.rollback()
