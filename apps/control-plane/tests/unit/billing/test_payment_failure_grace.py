"""T042 unit tests — payment_failure_grace service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from platform.billing.payment_failure_grace.models import (
    GraceResolution,
    PaymentFailureGrace,
)
from platform.billing.payment_failure_grace.service import (
    GRACE_WINDOW,
    PaymentFailureGraceService,
)
from platform.common.events.envelope import CorrelationContext


class FakeRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, PaymentFailureGrace] = {}

    async def find_open_for_subscription(self, subscription_id: UUID) -> PaymentFailureGrace | None:
        for grace in self.rows.values():
            if grace.subscription_id == subscription_id and grace.resolved_at is None:
                return grace
        return None

    async def open(
        self,
        *,
        tenant_id: UUID,
        subscription_id: UUID,
        started_at: datetime,
        grace_ends_at: datetime,
    ) -> PaymentFailureGrace:
        grace = PaymentFailureGrace(
            tenant_id=tenant_id,
            subscription_id=subscription_id,
            started_at=started_at,
            grace_ends_at=grace_ends_at,
            reminders_sent=0,
        )
        grace.id = uuid4()
        self.rows[grace.id] = grace
        return grace

    async def tick_reminder(self, grace_id: UUID, *, now: datetime) -> PaymentFailureGrace | None:
        grace = self.rows.get(grace_id)
        if grace is None or grace.resolved_at is not None:
            return None
        grace.reminders_sent += 1
        grace.last_reminder_at = now
        return grace

    async def resolve(
        self,
        grace_id: UUID,
        *,
        resolution: GraceResolution,
        now: datetime,
    ) -> PaymentFailureGrace | None:
        grace = self.rows.get(grace_id)
        if grace is None or grace.resolved_at is not None:
            return None
        grace.resolved_at = now
        grace.resolution = resolution.value
        return grace

    async def list_due_for_reminder(self, *, now: datetime) -> list[PaymentFailureGrace]:
        return [
            g
            for g in self.rows.values()
            if g.resolved_at is None and g.grace_ends_at > now
        ]

    async def list_due_for_expiry(self, *, now: datetime) -> list[PaymentFailureGrace]:
        return [
            g
            for g in self.rows.values()
            if g.resolved_at is None and g.grace_ends_at <= now
        ]


class FakeProducer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, *, topic: str, key: str, event_type: str, payload: dict, correlation_ctx: Any, source: str) -> None:
        del key, correlation_ctx, source
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload})


@pytest.mark.asyncio
async def test_start_grace_creates_open_row_and_emits_event() -> None:
    repo = FakeRepo()
    producer = FakeProducer()
    service = PaymentFailureGraceService(repository=repo, producer=producer)
    tenant = uuid4()
    sub = uuid4()
    correlation = CorrelationContext(correlation_id=uuid4())
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    grace = await service.start_grace(
        tenant_id=tenant,
        subscription_id=sub,
        correlation_ctx=correlation,
        now=now,
    )

    assert grace.subscription_id == sub
    assert grace.grace_ends_at == now + GRACE_WINDOW
    assert grace.resolved_at is None
    assert any(e["event_type"] == "billing.payment_failure_grace.opened" for e in producer.events)


@pytest.mark.asyncio
async def test_start_grace_idempotent_per_subscription() -> None:
    repo = FakeRepo()
    service = PaymentFailureGraceService(repository=repo, producer=FakeProducer())
    tenant = uuid4()
    sub = uuid4()
    correlation = CorrelationContext(correlation_id=uuid4())

    g1 = await service.start_grace(tenant_id=tenant, subscription_id=sub, correlation_ctx=correlation)
    g2 = await service.start_grace(tenant_id=tenant, subscription_id=sub, correlation_ctx=correlation)

    assert g1.id == g2.id
    assert len(repo.rows) == 1


@pytest.mark.asyncio
async def test_tick_reminders_fires_day_1_3_5_in_sequence() -> None:
    repo = FakeRepo()
    producer = FakeProducer()
    service = PaymentFailureGraceService(repository=repo, producer=producer)
    correlation = CorrelationContext(correlation_id=uuid4())
    started = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    sub = uuid4()
    grace = await service.start_grace(
        tenant_id=uuid4(),
        subscription_id=sub,
        correlation_ctx=correlation,
        now=started,
    )

    # Day 0 — no reminder due yet.
    ticked = await service.tick_reminders(correlation_ctx=correlation, now=started)
    assert ticked == []
    assert grace.reminders_sent == 0

    # Day 1 — fires first reminder.
    day1 = started + timedelta(days=1, minutes=1)
    ticked = await service.tick_reminders(correlation_ctx=correlation, now=day1)
    assert len(ticked) == 1
    assert grace.reminders_sent == 1

    # Day 2 — no new reminder (next is at day 3).
    day2 = started + timedelta(days=2)
    ticked = await service.tick_reminders(correlation_ctx=correlation, now=day2)
    assert ticked == []
    assert grace.reminders_sent == 1

    # Day 3 — second reminder.
    day3 = started + timedelta(days=3, minutes=1)
    await service.tick_reminders(correlation_ctx=correlation, now=day3)
    assert grace.reminders_sent == 2

    # Day 5 — third reminder.
    day5 = started + timedelta(days=5, minutes=1)
    await service.tick_reminders(correlation_ctx=correlation, now=day5)
    assert grace.reminders_sent == 3

    # Day 6 — no fourth reminder.
    day6 = started + timedelta(days=6)
    ticked = await service.tick_reminders(correlation_ctx=correlation, now=day6)
    assert ticked == []
    assert grace.reminders_sent == 3


@pytest.mark.asyncio
async def test_tick_expiries_resolves_with_downgrade() -> None:
    repo = FakeRepo()
    producer = FakeProducer()
    service = PaymentFailureGraceService(repository=repo, producer=producer)
    correlation = CorrelationContext(correlation_id=uuid4())
    started = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    sub = uuid4()
    grace = await service.start_grace(
        tenant_id=uuid4(),
        subscription_id=sub,
        correlation_ctx=correlation,
        now=started,
    )

    # Before expiry — no action.
    pre_expiry = started + timedelta(days=6)
    expired = await service.tick_expiries(correlation_ctx=correlation, now=pre_expiry)
    assert expired == []
    assert grace.resolved_at is None

    # After expiry — downgraded.
    post_expiry = started + timedelta(days=8)
    expired = await service.tick_expiries(correlation_ctx=correlation, now=post_expiry)
    assert len(expired) == 1
    assert expired[0].resolution == GraceResolution.downgraded_to_free.value
    resolution_events = [
        e for e in producer.events if e["event_type"] == "billing.payment_failure_grace.resolved"
    ]
    assert resolution_events
    assert resolution_events[-1]["payload"]["resolution"] == "downgraded_to_free"


@pytest.mark.asyncio
async def test_resolve_payment_recovered_closes_grace() -> None:
    repo = FakeRepo()
    producer = FakeProducer()
    service = PaymentFailureGraceService(repository=repo, producer=producer)
    correlation = CorrelationContext(correlation_id=uuid4())
    started = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    sub = uuid4()
    await service.start_grace(
        tenant_id=uuid4(),
        subscription_id=sub,
        correlation_ctx=correlation,
        now=started,
    )

    resolved = await service.resolve_payment_recovered(
        subscription_id=sub,
        correlation_ctx=correlation,
        now=started + timedelta(hours=1),
    )

    assert resolved is not None
    assert resolved.resolution == GraceResolution.payment_recovered.value
    assert resolved.resolved_at is not None
    resolution_events = [
        e for e in producer.events if e["event_type"] == "billing.payment_failure_grace.resolved"
    ]
    assert resolution_events
    assert resolution_events[-1]["payload"]["resolution"] == "payment_recovered"


@pytest.mark.asyncio
async def test_resolve_payment_recovered_no_open_grace_returns_none() -> None:
    service = PaymentFailureGraceService(
        repository=FakeRepo(),
        producer=FakeProducer(),
    )
    result = await service.resolve_payment_recovered(
        subscription_id=uuid4(),
        correlation_ctx=CorrelationContext(correlation_id=uuid4()),
    )
    assert result is None


@pytest.mark.asyncio
async def test_resolve_manually_marks_resolution() -> None:
    repo = FakeRepo()
    producer = FakeProducer()
    service = PaymentFailureGraceService(repository=repo, producer=producer)
    correlation = CorrelationContext(correlation_id=uuid4())
    grace = await service.start_grace(
        tenant_id=uuid4(),
        subscription_id=uuid4(),
        correlation_ctx=correlation,
    )

    resolved = await service.resolve_manually(
        grace_id=grace.id,
        correlation_ctx=correlation,
    )

    assert resolved is not None
    assert resolved.resolution == GraceResolution.manually_resolved.value
