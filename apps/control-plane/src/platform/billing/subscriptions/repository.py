from __future__ import annotations

from datetime import datetime
from platform.billing.subscriptions.models import Subscription
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


class SubscriptionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, subscription_id: UUID) -> Subscription | None:
        return await self.session.get(Subscription, subscription_id)

    async def get_by_scope(self, scope_type: str, scope_id: UUID) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.scope_type == scope_type, Subscription.scope_id == scope_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: UUID) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
        )
        return list(result.scalars().all())

    async def list_all(self, limit: int = 500) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .order_by(Subscription.created_at.desc(), Subscription.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        tenant_id: UUID,
        scope_type: str,
        scope_id: UUID,
        plan_id: UUID,
        plan_version: int,
        status: str,
        current_period_start: datetime,
        current_period_end: datetime,
        created_by_user_id: UUID | None = None,
        payment_method_id: UUID | None = None,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> Subscription:
        subscription = Subscription(
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            plan_id=plan_id,
            plan_version=plan_version,
            status=status,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            created_by_user_id=created_by_user_id,
            payment_method_id=payment_method_id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
        )
        self.session.add(subscription)
        await self.session.flush()
        return subscription

    async def update_status(self, subscription_id: UUID, status: str) -> Subscription | None:
        result = await self.session.execute(
            update(Subscription)
            .where(Subscription.id == subscription_id)
            .values(status=status)
            .returning(Subscription)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def update_plan_pinning(
        self,
        subscription_id: UUID,
        *,
        plan_id: UUID,
        plan_version: int,
        current_period_start: datetime | None = None,
        current_period_end: datetime | None = None,
        payment_method_id: UUID | None = None,
        status: str | None = None,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
    ) -> Subscription | None:
        values: dict[str, object] = {"plan_id": plan_id, "plan_version": plan_version}
        if current_period_start is not None:
            values["current_period_start"] = current_period_start
        if current_period_end is not None:
            values["current_period_end"] = current_period_end
        if payment_method_id is not None:
            values["payment_method_id"] = payment_method_id
        if status is not None:
            values["status"] = status
        if stripe_customer_id is not None:
            values["stripe_customer_id"] = stripe_customer_id
        if stripe_subscription_id is not None:
            values["stripe_subscription_id"] = stripe_subscription_id
        result = await self.session.execute(
            update(Subscription)
            .where(Subscription.id == subscription_id)
            .values(**values)
            .returning(Subscription)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def set_cancel_at_period_end(
        self,
        subscription_id: UUID,
        cancel_at_period_end: bool,
    ) -> Subscription | None:
        result = await self.session.execute(
            update(Subscription)
            .where(Subscription.id == subscription_id)
            .values(
                cancel_at_period_end=cancel_at_period_end,
                status="cancellation_pending" if cancel_at_period_end else "active",
            )
            .returning(Subscription)
        )
        await self.session.flush()
        return result.scalar_one_or_none()

    async def list_due_for_period_rollover(
        self,
        now: datetime,
        *,
        limit: int = 500,
    ) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.current_period_end <= now,
                Subscription.status.not_in(("canceled", "suspended")),
            )
            .order_by(Subscription.current_period_end.asc(), Subscription.id.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())

    async def advance_period(
        self,
        subscription: Subscription,
        *,
        new_period_start: datetime,
        new_period_end: datetime,
        status: str | None = None,
    ) -> Subscription:
        subscription.current_period_start = new_period_start
        subscription.current_period_end = new_period_end
        if status is not None:
            subscription.status = status
        if status == "canceled":
            subscription.cancel_at_period_end = False
        await self.session.flush()
        return subscription

    async def count_by_plan_version(self, plan_id: UUID, plan_version: int) -> int:
        result = await self.session.execute(
            select(Subscription.id).where(
                Subscription.plan_id == plan_id,
                Subscription.plan_version == plan_version,
            )
        )
        return len(result.scalars().all())
