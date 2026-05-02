from __future__ import annotations

from platform.billing.plans.repository import PlansRepository
from platform.billing.providers.stub_provider import StubPaymentProvider
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.service import SubscriptionService

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    async def append(self, *args: object, **kwargs: object) -> None:
        self.entries.append(dict(kwargs))


class _Producer:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    async def publish(self, *args: object) -> None:
        self.events.append(args)


async def test_upgrade_free_to_pro_updates_subscription_atomically(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session, plan_slug="free")
        audit = _Audit()
        producer = _Producer()
        service = SubscriptionService(
            session=session,
            subscriptions=SubscriptionsRepository(session),
            plans=PlansRepository(session),
            payment_provider=StubPaymentProvider(),
            audit_chain=audit,  # type: ignore[arg-type]
            producer=producer,  # type: ignore[arg-type]
        )

        updated = await service.upgrade(
            fixture.workspace_id,
            "pro",
            "stub_pm_test",
            actor_id=fixture.owner_id,
        )
        plan_slug = await session.scalar(
            text("SELECT slug FROM plans WHERE id = :plan_id"),
            {"plan_id": str(updated.plan_id)},
        )

        assert plan_slug == "pro"
        assert updated.plan_version >= 1
        assert updated.current_period_end > updated.current_period_start
        assert updated.payment_method_id is not None
        assert audit.entries[0]["event_type"] == "billing.subscription.upgraded"
        assert producer.events[0][2] == "billing.subscription.upgraded"

        await session.rollback()
