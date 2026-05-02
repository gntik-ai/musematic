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


async def test_metering_pipeline_counts_and_deduplicates_compute_end_events(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        fixture = await create_workspace_subscription(session, plan_slug="pro")
        job = MeteringJob(session=session, settings=PlatformSettings())
        started = datetime.now(UTC).replace(microsecond=0)
        events = [
            _event(
                fixture.workspace_id,
                fixture.tenant_id,
                started + timedelta(minutes=index),
                started + timedelta(minutes=index, seconds=30 + index),
            )
            for index in range(100)
        ]

        for envelope in events:
            result = await job.process_event(envelope)
            assert result.processed is True
        for envelope in events:
            result = await job.process_event(envelope)
            assert result.processed is False

        rows = await session.execute(
            text(
                """
                SELECT metric, quantity
                  FROM usage_records
                 WHERE subscription_id = :subscription_id
                   AND is_overage = false
                 ORDER BY metric
                """
            ),
            {"subscription_id": str(fixture.subscription_id)},
        )
        usage = {str(metric): Decimal(quantity) for metric, quantity in rows.all()}
        processed_count = await session.scalar(text("SELECT count(*) FROM processed_event_ids"))

        assert usage["executions"] == Decimal("100.0000")
        assert usage["minutes"] == sum(
            (Decimal(str(30 + index)) / Decimal("60")).quantize(Decimal("0.0001"))
            for index in range(100)
        )
        assert processed_count == 100

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
            "active_started_at": start_ts.isoformat(),
            "active_ended_at": end_ts.isoformat(),
        },
    )
