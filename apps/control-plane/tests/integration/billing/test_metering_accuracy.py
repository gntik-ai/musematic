from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.billing.quotas.metering import MeteringJob
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.billing_quota_support import create_workspace_subscription

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class _PaymentProvider:
    def __init__(self) -> None:
        self.reported: list[tuple[Decimal, str]] = []

    async def report_usage(
        self,
        provider_subscription_id: str,
        quantity: Decimal,
        idempotency_key: str,
    ) -> None:
        del provider_subscription_id
        self.reported.append((quantity, idempotency_key))


async def test_metering_accuracy_and_overage_usage_reporting(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(
            session,
            plan_slug="pro",
            minutes=Decimal("2399.0000"),
        )
        payment_provider = _PaymentProvider()
        job = MeteringJob(
            session=session,
            settings=PlatformSettings(),
            payment_provider=payment_provider,  # type: ignore[arg-type]
        )
        started = datetime.now(UTC).replace(microsecond=0)
        durations = [5 + (index * 175 / 99) for index in range(100)]
        expected = Decimal("0")

        for index, seconds in enumerate(durations):
            event = _event(
                fixture.workspace_id,
                fixture.tenant_id,
                started + timedelta(minutes=index),
                started + timedelta(minutes=index, seconds=seconds),
            )
            result = await job.process_event(event)
            expected += result.minutes

        usage = await session.scalar(
            text(
                """
                SELECT quantity
                  FROM usage_records
                 WHERE subscription_id = :subscription_id
                   AND metric = 'minutes'
                   AND is_overage = false
                """
            ),
            {"subscription_id": str(fixture.subscription_id)},
        )
        overage = await session.scalar(
            text(
                """
                SELECT quantity
                  FROM usage_records
                 WHERE subscription_id = :subscription_id
                   AND metric = 'minutes'
                   AND is_overage = true
                """
            ),
            {"subscription_id": str(fixture.subscription_id)},
        )

        assert abs(Decimal(usage) - (Decimal("2399.0000") + expected)) <= expected * Decimal("0.02")
        assert Decimal(overage) == (Decimal("2399.0000") + expected - Decimal("2400.0000"))
        assert payment_provider.reported
        assert len({idempotency_key for _, idempotency_key in payment_provider.reported}) == len(
            payment_provider.reported
        )

        await session.rollback()


def _event(
    workspace_id: object,
    tenant_id: object,
    start_ts: datetime,
    end_ts: datetime,
) -> EventEnvelope:
    event_id = uuid4()
    return EventEnvelope(
        event_type="execution.compute.end",
        source="execution-runtime",
        correlation_context=CorrelationContext(
            correlation_id=uuid4(),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            execution_id=event_id,
        ),
        payload={
            "event_id": str(event_id),
            "start_ts": start_ts.isoformat(),
            "end_ts": end_ts.isoformat(),
        },
    )
