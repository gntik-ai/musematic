from __future__ import annotations

from platform.billing.plans.repository import PlansRepository
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.service import SubscriptionService

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _Producer:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    async def publish(self, *args: object) -> None:
        self.events.append(args)


async def test_downgrade_scheduled_sets_cancellation_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session, plan_slug="pro")
        producer = _Producer()
        service = SubscriptionService(
            session=session,
            subscriptions=SubscriptionsRepository(session),
            plans=PlansRepository(session),
            producer=producer,  # type: ignore[arg-type]
        )

        updated = await service.downgrade_at_period_end(fixture.subscription_id, "free")

        assert updated.status == "cancellation_pending"
        assert updated.cancel_at_period_end is True
        assert producer.events[0][2] == "billing.subscription.downgrade_scheduled"

        await session.rollback()
