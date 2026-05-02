from __future__ import annotations

from platform.billing.subscriptions.period_scheduler import _data_exceeding_free_limits
from platform.billing.subscriptions.repository import SubscriptionsRepository

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription, insert_published_agents

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_downgrade_cleanup_flag_reports_data_above_free_limits(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(
            session,
            plan_slug="pro",
            member_count=4,
        )
        await insert_published_agents(
            session,
            tenant_id=fixture.tenant_id,
            workspace_id=fixture.workspace_id,
            created_by=fixture.owner_id,
            count=6,
        )
        subscription = await SubscriptionsRepository(session).get_by_id(fixture.subscription_id)
        assert subscription is not None

        cleanup = await _data_exceeding_free_limits(session, subscription)

        assert cleanup == {"workspaces": 0, "agents": 1, "users": 1}

        await session.rollback()
