from __future__ import annotations

from platform.billing.plans.repository import PlansRepository
from platform.billing.quotas.enforcer import QuotaEnforcer
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.service import SubscriptionService
from platform.common.config import PlatformSettings

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_upgrade_applies_pro_quotas_to_next_chargeable_action(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session, plan_slug="free", executions=100)
        before = await QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
        ).check_execution(fixture.workspace_id)
        service = SubscriptionService(
            session=session,
            subscriptions=SubscriptionsRepository(session),
            plans=PlansRepository(session),
        )

        await service.upgrade(fixture.workspace_id, "pro", None, actor_id=fixture.owner_id)
        after = await QuotaEnforcer(
            session=session,
            settings=PlatformSettings(),
        ).check_execution(fixture.workspace_id)

        assert before.decision == "HARD_CAP_EXCEEDED"
        assert after.decision == "OK"

        await session.rollback()
