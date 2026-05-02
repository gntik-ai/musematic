from __future__ import annotations

from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription, insert_published_agents

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_free_agent_publish_cap_blocks_next_published_agent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session)
        await insert_published_agents(
            session,
            tenant_id=fixture.tenant_id,
            workspace_id=fixture.workspace_id,
            created_by=fixture.owner_id,
            count=5,
        )
        enforcer = QuotaEnforcer(session=session, settings=PlatformSettings())

        result = await enforcer.check_agent_publish(fixture.workspace_id)

        assert result.decision == "HARD_CAP_EXCEEDED"
        assert result.quota_name == "max_agents_per_workspace"
        assert result.current == 6
        assert result.limit == 5
        assert result.plan_slug == "free"

        await session.rollback()
