from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.context_engineering.events import (
    AssemblyCompletedPayload,
    BudgetExceededMinimumPayload,
    ContextEngineeringEventType,
    DriftDetectedPayload,
    publish_assembly_completed,
    publish_budget_exceeded_minimum,
    publish_drift_detected,
    register_context_engineering_event_types,
)
from uuid import uuid4

import pytest

from tests.context_engineering_support import EventProducerStub


@pytest.mark.asyncio
async def test_context_engineering_events_register_and_publish() -> None:
    register_context_engineering_event_types()
    producer = EventProducerStub()
    correlation = CorrelationContext(correlation_id=uuid4(), workspace_id=uuid4())

    await publish_assembly_completed(
        producer,
        AssemblyCompletedPayload(
            assembly_id=uuid4(),
            workspace_id=correlation.workspace_id,
            execution_id=uuid4(),
            step_id=uuid4(),
            agent_fqn="finance:agent",
            quality_score=0.8,
            token_count=100,
            flags=[],
            created_at=datetime.now(UTC),
        ),
        correlation,
    )
    await publish_budget_exceeded_minimum(
        producer,
        BudgetExceededMinimumPayload(
            workspace_id=correlation.workspace_id,
            execution_id=uuid4(),
            step_id=uuid4(),
            agent_fqn="finance:agent",
            max_tokens=10,
            minimum_tokens=12,
        ),
        correlation,
    )
    await publish_drift_detected(
        producer,
        DriftDetectedPayload(
            alert_id=uuid4(),
            workspace_id=correlation.workspace_id,
            agent_fqn="finance:agent",
            historical_mean=0.8,
            historical_stddev=0.1,
            recent_mean=0.4,
            degradation_delta=0.4,
        ),
        correlation,
    )

    assert [item["event_type"] for item in producer.published] == [
        ContextEngineeringEventType.assembly_completed.value,
        ContextEngineeringEventType.budget_exceeded_minimum.value,
        ContextEngineeringEventType.drift_detected.value,
    ]


@pytest.mark.asyncio
async def test_context_engineering_publishers_noop_without_producer() -> None:
    correlation = CorrelationContext(correlation_id=uuid4(), workspace_id=uuid4())

    await publish_budget_exceeded_minimum(
        None,
        BudgetExceededMinimumPayload(
            workspace_id=correlation.workspace_id,
            execution_id=uuid4(),
            step_id=uuid4(),
            agent_fqn="finance:agent",
            max_tokens=1,
            minimum_tokens=2,
        ),
        correlation,
    )
