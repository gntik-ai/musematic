from __future__ import annotations

from platform.billing.exceptions import UpgradeFailedError
from platform.billing.plans.repository import PlansRepository
from platform.billing.subscriptions.repository import SubscriptionsRepository
from platform.billing.subscriptions.service import SubscriptionService

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _FailingProvider:
    async def create_customer(self, *args: object) -> str:
        return "stub_customer"

    async def attach_payment_method(self, *args: object) -> str:
        raise RuntimeError("payment method rejected")


class _Audit:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    async def append(self, *args: object, **kwargs: object) -> None:
        self.entries.append(dict(kwargs))


async def test_upgrade_payment_method_failure_keeps_subscription_on_free(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session, plan_slug="free")
        audit = _Audit()
        service = SubscriptionService(
            session=session,
            subscriptions=SubscriptionsRepository(session),
            plans=PlansRepository(session),
            payment_provider=_FailingProvider(),  # type: ignore[arg-type]
            audit_chain=audit,  # type: ignore[arg-type]
        )

        with pytest.raises(UpgradeFailedError):
            await service.upgrade(
                fixture.workspace_id,
                "pro",
                "bad_pm",
                actor_id=fixture.owner_id,
            )
        plan_slug = await session.scalar(
            text(
                """
                SELECT p.slug
                  FROM subscriptions s
                  JOIN plans p ON p.id = s.plan_id
                 WHERE s.id = :subscription_id
                """
            ),
            {"subscription_id": str(fixture.subscription_id)},
        )

        assert plan_slug == "free"
        assert audit.entries == []

        await session.rollback()
