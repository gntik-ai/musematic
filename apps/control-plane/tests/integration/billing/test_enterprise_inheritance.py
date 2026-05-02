from __future__ import annotations

from platform.billing.subscriptions.resolver import SubscriptionResolver

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_enterprise_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_enterprise_workspaces_inherit_tenant_subscription(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_enterprise_workspace_subscription(session, workspace_count=3)
        workspace_ids = (
            await session.execute(
                text(
                    """
                    SELECT id
                      FROM workspaces_workspaces
                     WHERE tenant_id = :tenant_id
                     ORDER BY name ASC
                    """
                ),
                {"tenant_id": str(fixture.tenant_id)},
            )
        ).scalars().all()
        resolver = SubscriptionResolver(session)
        subscriptions = [
            await resolver.resolve_active_subscription(workspace_id)
            for workspace_id in workspace_ids
        ]

        assert {subscription.id for subscription in subscriptions} == {fixture.subscription_id}
        assert {subscription.scope_type for subscription in subscriptions} == {"tenant"}

        await session.rollback()
