from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class WorkflowEventType(StrEnum):
    """Represent the workflow event type."""
    workflow_published = "workflows.workflow.published"
    trigger_fired = "workflows.trigger.fired"


class WorkflowPublishedEvent(BaseModel):
    """Represent the workflow published event payload."""
    workflow_id: UUID
    version_id: UUID
    version_number: int
    workspace_id: UUID
    schema_version: int


class TriggerFiredEvent(BaseModel):
    """Represent the trigger fired event payload."""
    workflow_id: UUID
    trigger_id: UUID
    trigger_type: str
    execution_id: UUID | None = None


WORKFLOW_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    WorkflowEventType.workflow_published.value: WorkflowPublishedEvent,
    WorkflowEventType.trigger_fired.value: TriggerFiredEvent,
}


def register_workflows_event_types() -> None:
    """Register workflows event types."""
    for event_type, schema in WORKFLOW_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_workflow_published(
    producer: EventProducer | None,
    event: WorkflowPublishedEvent,
    correlation_ctx: CorrelationContext,
) -> None:
    """Publish workflow published."""
    if producer is None:
        return
    await producer.publish(
        topic="workflow.triggers",
        key=str(event.workflow_id),
        event_type=WorkflowEventType.workflow_published.value,
        payload=event.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.workflows",
    )


async def publish_trigger_fired(
    producer: EventProducer | None,
    event: TriggerFiredEvent,
    correlation_ctx: CorrelationContext,
) -> None:
    """Publish trigger fired."""
    if producer is None:
        return
    await producer.publish(
        topic="workflow.triggers",
        key=str(event.workflow_id),
        event_type=WorkflowEventType.trigger_fired.value,
        payload=event.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.workflows",
    )
