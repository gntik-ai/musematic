from __future__ import annotations

from decimal import Decimal
from platform.common.config import PlatformSettings
from platform.cost_governance.services.attribution_service import AttributionService
from uuid import uuid4

import pytest

from tests.integration.cost_governance.support import (
    AttributionRepository,
    ClickHouseSink,
    RecordingProducer,
)


@pytest.mark.asyncio
async def test_execution_runtime_event_records_pg_clickhouse_and_kafka_attribution() -> None:
    repository = AttributionRepository()
    clickhouse = ClickHouseSink()
    producer = RecordingProducer()
    service = AttributionService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(
            cost_governance={
                "compute_cost_per_ms_cents": 0.01,
                "storage_cost_per_byte_cents": 0.001,
            }
        ),
        clickhouse_repository=clickhouse,  # type: ignore[arg-type]
        kafka_producer=producer,  # type: ignore[arg-type]
        fail_open=False,
    )

    row = await service.record_step_cost(
        execution_id=uuid4(),
        step_id="model-call",
        workspace_id=uuid4(),
        agent_id=uuid4(),
        user_id=uuid4(),
        payload={
            "model_id": "gpt-test",
            "tokens_in": 1000,
            "tokens_out": 500,
            "input_cost_per_1k_tokens": "2",
            "output_cost_per_1k_tokens": "4",
            "duration_ms": 10,
            "bytes_written": 20,
        },
    )
    await clickhouse.flush()

    assert row is not None
    assert len(repository.rows) == 1
    assert len(clickhouse.rows) == 1
    assert producer.events[0]["event_type"] == "cost.execution.attributed"
    assert row.total_cost_cents == (
        row.model_cost_cents
        + row.compute_cost_cents
        + row.storage_cost_cents
        + row.overhead_cost_cents
    )
    assert row.total_cost_cents == Decimal("4.1200")
