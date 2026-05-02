from __future__ import annotations

import asyncio
from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription, set_tenant

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_free_execution_cap_rejects_1000_parallel_overrun_attempts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as setup_session:
        fixture = await create_workspace_subscription(setup_session, executions=100)
        await setup_session.commit()

    semaphore = asyncio.Semaphore(50)

    async def attempt() -> str:
        async with semaphore:
            async with session_factory() as session:
                await set_tenant(session, fixture.tenant_id)
                result = await QuotaEnforcer(
                    session=session,
                    settings=PlatformSettings(),
                ).check_execution(fixture.workspace_id)
                await session.rollback()
                return result.decision

    decisions = await asyncio.gather(*(attempt() for _ in range(1000)))

    async with session_factory() as verify_session:
        await set_tenant(verify_session, fixture.tenant_id)
        execution_count = await verify_session.scalar(
            text("SELECT count(*) FROM executions WHERE workspace_id = :workspace_id"),
            {"workspace_id": str(fixture.workspace_id)},
        )
        await verify_session.rollback()

    assert set(decisions) == {"HARD_CAP_EXCEEDED"}
    assert execution_count == 0
