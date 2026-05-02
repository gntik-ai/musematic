from __future__ import annotations

import statistics
import time
from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_enterprise_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_enterprise_quota_check_cached_overhead_under_one_ms_p95(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_enterprise_workspace_subscription(session)
        enforcer = QuotaEnforcer(session=session, settings=PlatformSettings())
        await enforcer.check_execution(fixture.workspace_id)

        samples: list[float] = []
        for _ in range(10000):
            start = time.perf_counter()
            result = await enforcer.check_execution(fixture.workspace_id)
            samples.append((time.perf_counter() - start) * 1000)
            assert result.decision == "OK"

        p95 = statistics.quantiles(samples, n=20)[18]
        assert p95 < 1.0

        await session.rollback()
