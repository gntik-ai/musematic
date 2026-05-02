from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.common.config import PlatformSettings
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_enterprise_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _CountingUsageRepository:
    def __init__(self) -> None:
        self.calls = 0

    async def get_current_usage(
        self,
        subscription_id: UUID,
        period_start: datetime,
    ) -> dict[str, Decimal]:
        del subscription_id, period_start
        self.calls += 1
        return {"executions": Decimal("100000"), "minutes": Decimal("100000")}


async def test_enterprise_unlimited_short_circuits_usage_cache(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_enterprise_workspace_subscription(session)
        usage = _CountingUsageRepository()
        enforcer = QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
            usage_repository=usage,  # type: ignore[arg-type]
        )

        decisions = [
            (await enforcer.check_execution(fixture.workspace_id)).decision for _ in range(1000)
        ]

        assert set(decisions) == {"OK"}
        assert usage.calls == 0

        await session.rollback()
