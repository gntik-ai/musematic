from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from platform.workflows.events import (
    TriggerFiredEvent,
    WorkflowEventType,
    WorkflowPublishedEvent,
    publish_trigger_fired,
    publish_workflow_published,
    register_workflows_event_types,
)
from uuid import uuid4

import pytest

from tests.workflow_execution_support import FakeProducer


@pytest.mark.asyncio
async def test_workflow_events_register_and_publish_expected_payloads() -> None:
    producer = FakeProducer()
    correlation = CorrelationContext(workspace_id=uuid4(), correlation_id=uuid4())
    workflow_id = uuid4()
    register_workflows_event_types()

    await publish_workflow_published(
        producer,
        WorkflowPublishedEvent(
            workflow_id=workflow_id,
            version_id=uuid4(),
            version_number=2,
            workspace_id=uuid4(),
            schema_version=1,
        ),
        correlation,
    )
    await publish_trigger_fired(
        producer,
        TriggerFiredEvent(
            workflow_id=workflow_id,
            trigger_id=uuid4(),
            trigger_type="webhook",
            execution_id=uuid4(),
        ),
        correlation,
    )

    assert event_registry.is_registered(WorkflowEventType.workflow_published.value) is True
    assert event_registry.is_registered(WorkflowEventType.trigger_fired.value) is True
    assert [message["event_type"] for message in producer.messages] == [
        WorkflowEventType.workflow_published.value,
        WorkflowEventType.trigger_fired.value,
    ]


@pytest.mark.asyncio
async def test_workflow_event_publishers_ignore_missing_producer() -> None:
    correlation = CorrelationContext(workspace_id=uuid4(), correlation_id=uuid4())

    await publish_workflow_published(
        None,
        WorkflowPublishedEvent(
            workflow_id=uuid4(),
            version_id=uuid4(),
            version_number=1,
            workspace_id=uuid4(),
            schema_version=1,
        ),
        correlation,
    )
    await publish_trigger_fired(
        None,
        TriggerFiredEvent(
            workflow_id=uuid4(),
            trigger_id=uuid4(),
            trigger_type="cron",
            execution_id=None,
        ),
        correlation,
    )
