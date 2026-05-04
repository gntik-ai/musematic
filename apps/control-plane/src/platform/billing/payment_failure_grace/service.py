"""UPD-052 — payment_failure_grace service layer.

Drives the 7-day grace state machine (research R8):

- ``start_grace(subscription_id)`` — opens a grace row on first
  ``invoice.payment_failed``. Idempotent: if a grace is already open for
  the subscription, returns it unchanged.
- ``tick_reminders(now)`` — scans open graces, dispatches reminder N when
  ``now >= started_at + N*2d`` (day-1, day-3, day-5).
- ``tick_expiries(now)`` — scans graces whose ``grace_ends_at`` has passed,
  marks them ``downgraded_to_free``, and emits the resolution event.
- ``resolve_payment_recovered(subscription_id)`` — Stripe-side payment
  retry succeeded; close the grace.
- ``resolve_manually(grace_id, note)`` — operator override.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.billing.events import (
    BillingEventType,
    PaymentFailureGraceOpenedPayload,
    PaymentFailureGraceResolvedPayload,
    publish_billing_event,
)
from platform.billing.metrics import metrics
from platform.billing.payment_failure_grace.models import (
    GraceResolution,
    PaymentFailureGrace,
)
from platform.billing.payment_failure_grace.repository import (
    PaymentFailureGraceRepository,
)
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from uuid import UUID

LOGGER = get_logger(__name__)

# Reminder cadence — day-1/3/5 (research R8). The service emits at most one
# reminder per cron tick.
REMINDER_INTERVALS = (
    timedelta(days=1),
    timedelta(days=3),
    timedelta(days=5),
)
GRACE_WINDOW = timedelta(days=7)


class PaymentFailureGraceService:
    def __init__(
        self,
        *,
        repository: PaymentFailureGraceRepository,
        producer: EventProducer | None,
    ) -> None:
        self.repo = repository
        self.producer = producer

    async def start_grace(
        self,
        *,
        tenant_id: UUID,
        subscription_id: UUID,
        correlation_ctx: CorrelationContext,
        now: datetime | None = None,
    ) -> PaymentFailureGrace:
        moment = now or datetime.now(UTC)
        existing = await self.repo.find_open_for_subscription(subscription_id)
        if existing is not None:
            return existing
        grace = await self.repo.open(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            started_at=moment,
            grace_ends_at=moment + GRACE_WINDOW,
        )
        metrics.adjust_payment_failure_grace_open(1)
        await publish_billing_event(
            self.producer,
            BillingEventType.payment_failure_grace_opened,
            PaymentFailureGraceOpenedPayload(
                grace_id=grace.id,
                subscription_id=subscription_id,
                started_at=grace.started_at,
                grace_ends_at=grace.grace_ends_at,
                correlation_context=correlation_ctx,
            ),
            correlation_ctx,
            partition_key=tenant_id,
        )
        LOGGER.info(
            "billing.grace_opened",
            grace_id=str(grace.id),
            subscription_id=str(subscription_id),
            grace_ends_at=grace.grace_ends_at.isoformat(),
        )
        return grace

    async def tick_reminders(
        self,
        *,
        correlation_ctx: CorrelationContext,
        now: datetime | None = None,
    ) -> list[PaymentFailureGrace]:
        """Send the next reminder for any open grace whose tick is due."""
        moment = now or datetime.now(UTC)
        due_graces = await self.repo.list_due_for_reminder(now=moment)
        ticked: list[PaymentFailureGrace] = []
        for grace in due_graces:
            next_idx = grace.reminders_sent  # 0/1/2
            if next_idx >= len(REMINDER_INTERVALS):
                continue
            target_time = grace.started_at + REMINDER_INTERVALS[next_idx]
            if moment < target_time:
                continue
            updated = await self.repo.tick_reminder(grace.id, now=moment)
            if updated is None:
                continue
            ticked.append(updated)
            LOGGER.info(
                "billing.grace_reminder_sent",
                grace_id=str(updated.id),
                subscription_id=str(updated.subscription_id),
                reminder_index=updated.reminders_sent,
            )
        return ticked

    async def tick_expiries(
        self,
        *,
        correlation_ctx: CorrelationContext,
        now: datetime | None = None,
    ) -> list[PaymentFailureGrace]:
        """Resolve any open grace whose 7-day window has elapsed."""
        moment = now or datetime.now(UTC)
        due_graces = await self.repo.list_due_for_expiry(now=moment)
        resolved: list[PaymentFailureGrace] = []
        for grace in due_graces:
            updated = await self.repo.resolve(
                grace.id,
                resolution=GraceResolution.downgraded_to_free,
                now=moment,
            )
            if updated is None:
                continue
            metrics.adjust_payment_failure_grace_open(-1)
            await publish_billing_event(
                self.producer,
                BillingEventType.payment_failure_grace_resolved,
                PaymentFailureGraceResolvedPayload(
                    grace_id=updated.id,
                    subscription_id=updated.subscription_id,
                    resolved_at=moment,
                    resolution=GraceResolution.downgraded_to_free.value,
                    correlation_context=correlation_ctx,
                ),
                correlation_ctx,
                partition_key=updated.tenant_id,
            )
            resolved.append(updated)
            LOGGER.warning(
                "billing.grace_expired_downgrade",
                grace_id=str(updated.id),
                subscription_id=str(updated.subscription_id),
            )
        return resolved

    async def resolve_payment_recovered(
        self,
        *,
        subscription_id: UUID,
        correlation_ctx: CorrelationContext,
        now: datetime | None = None,
    ) -> PaymentFailureGrace | None:
        moment = now or datetime.now(UTC)
        grace = await self.repo.find_open_for_subscription(subscription_id)
        if grace is None:
            return None
        updated = await self.repo.resolve(
            grace.id,
            resolution=GraceResolution.payment_recovered,
            now=moment,
        )
        if updated is None:
            return None
        metrics.adjust_payment_failure_grace_open(-1)
        await publish_billing_event(
            self.producer,
            BillingEventType.payment_failure_grace_resolved,
            PaymentFailureGraceResolvedPayload(
                grace_id=updated.id,
                subscription_id=subscription_id,
                resolved_at=moment,
                resolution=GraceResolution.payment_recovered.value,
                correlation_context=correlation_ctx,
            ),
            correlation_ctx,
            partition_key=updated.tenant_id,
        )
        LOGGER.info(
            "billing.grace_recovered",
            grace_id=str(updated.id),
            subscription_id=str(subscription_id),
        )
        return updated

    async def resolve_manually(
        self,
        *,
        grace_id: UUID,
        correlation_ctx: CorrelationContext,
        now: datetime | None = None,
    ) -> PaymentFailureGrace | None:
        moment = now or datetime.now(UTC)
        updated = await self.repo.resolve(
            grace_id,
            resolution=GraceResolution.manually_resolved,
            now=moment,
        )
        if updated is None:
            return None
        metrics.adjust_payment_failure_grace_open(-1)
        await publish_billing_event(
            self.producer,
            BillingEventType.payment_failure_grace_resolved,
            PaymentFailureGraceResolvedPayload(
                grace_id=updated.id,
                subscription_id=updated.subscription_id,
                resolved_at=moment,
                resolution=GraceResolution.manually_resolved.value,
                correlation_context=correlation_ctx,
            ),
            correlation_ctx,
            partition_key=updated.tenant_id,
        )
        return updated
