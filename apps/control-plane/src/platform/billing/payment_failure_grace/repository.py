"""Repository for the ``payment_failure_grace`` table (UPD-052)."""

from __future__ import annotations

from datetime import datetime
from platform.billing.payment_failure_grace.models import (
    GraceResolution,
    PaymentFailureGrace,
)
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class PaymentFailureGraceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_open_for_subscription(
        self,
        subscription_id: UUID,
    ) -> PaymentFailureGrace | None:
        stmt = select(PaymentFailureGrace).where(
            PaymentFailureGrace.subscription_id == subscription_id,
            PaymentFailureGrace.resolved_at.is_(None),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def open(
        self,
        *,
        tenant_id: UUID,
        subscription_id: UUID,
        started_at: datetime,
        grace_ends_at: datetime,
    ) -> PaymentFailureGrace:
        existing = await self.find_open_for_subscription(subscription_id)
        if existing is not None:
            return existing
        record = PaymentFailureGrace(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            started_at=started_at,
            grace_ends_at=grace_ends_at,
            reminders_sent=0,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def tick_reminder(
        self,
        grace_id: UUID,
        *,
        now: datetime,
    ) -> PaymentFailureGrace | None:
        grace = await self.session.get(PaymentFailureGrace, grace_id)
        if grace is None or grace.resolved_at is not None:
            return None
        grace.reminders_sent += 1
        grace.last_reminder_at = now
        await self.session.flush()
        return grace

    async def resolve(
        self,
        grace_id: UUID,
        *,
        resolution: GraceResolution,
        now: datetime,
    ) -> PaymentFailureGrace | None:
        grace = await self.session.get(PaymentFailureGrace, grace_id)
        if grace is None or grace.resolved_at is not None:
            return None
        grace.resolved_at = now
        grace.resolution = resolution.value
        await self.session.flush()
        return grace

    async def list_due_for_reminder(
        self,
        *,
        now: datetime,
    ) -> list[PaymentFailureGrace]:
        """Return open graces that need their next reminder dispatched.

        A reminder is due when ``reminders_sent < 3`` AND
        ``now >= started_at + (reminders_sent + 1) * 2 days`` (day-1, day-3, day-5).
        The decision is encoded in the service layer because SQL date math
        across PostgreSQL would tie the repo to a specific dialect.
        """
        stmt = (
            select(PaymentFailureGrace)
            .where(
                PaymentFailureGrace.resolved_at.is_(None),
                PaymentFailureGrace.grace_ends_at > now,
            )
            .order_by(PaymentFailureGrace.started_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_due_for_expiry(
        self,
        *,
        now: datetime,
    ) -> list[PaymentFailureGrace]:
        """Return open graces whose grace_ends_at has passed."""
        stmt = (
            select(PaymentFailureGrace)
            .where(
                PaymentFailureGrace.resolved_at.is_(None),
                PaymentFailureGrace.grace_ends_at <= now,
            )
            .order_by(PaymentFailureGrace.grace_ends_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())
