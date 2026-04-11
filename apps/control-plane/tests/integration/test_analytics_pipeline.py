from __future__ import annotations

from platform.analytics.consumer import AnalyticsPipelineConsumer
from platform.common.config import PlatformSettings
from uuid import uuid4

import pytest

from tests.analytics_support import ClickHouseClientStub, build_cost_model, build_envelope

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_pipeline_buffers_runtime_and_quality_events_into_clickhouse_batches() -> None:
    clickhouse = ClickHouseClientStub()
    consumer = AnalyticsPipelineConsumer(
        settings=PlatformSettings(),
        clickhouse_client=clickhouse,  # type: ignore[arg-type]
    )
    consumer._pricing_cache["gpt-4o"] = build_cost_model()

    await consumer._buffer_event(
        "workflow.runtime",
        build_envelope(
            workspace_id=uuid4(),
            execution_id=uuid4(),
            payload={
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "input_tokens": 100,
                "output_tokens": 25,
            },
        ),
    )
    await consumer._buffer_event(
        "evaluation.events",
        build_envelope(
            workspace_id=uuid4(),
            execution_id=uuid4(),
            payload={
                "agent_fqn": "planner:daily",
                "model_id": "gpt-4o",
                "quality_score": 0.9,
            },
        ),
    )
    await consumer._flush_buffers()

    assert clickhouse.insert_calls[0][0] == "analytics_usage_events"
    assert clickhouse.insert_calls[1][0] == "analytics_quality_events"
