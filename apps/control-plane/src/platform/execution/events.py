from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Final
from uuid import UUID

from pydantic import BaseModel


class ExecutionDomainEventType(StrEnum):
    execution_created = "execution.created"
    execution_status_changed = "execution.status_changed"
    execution_reprioritized = "execution.reprioritized"


class ExecutionCreatedEvent(BaseModel):
    execution_id: UUID
    workflow_definition_id: UUID
    workflow_version_id: UUID
    workspace_id: UUID


class ExecutionStatusChangedEvent(BaseModel):
    execution_id: UUID
    status: str
    step_id: str | None = None


class ExecutionReprioritizedEvent(BaseModel):
    execution_id: UUID
    trigger_reason: str
    steps_affected: list[str]


EXECUTION_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    ExecutionDomainEventType.execution_created.value: ExecutionCreatedEvent,
    ExecutionDomainEventType.execution_status_changed.value: ExecutionStatusChangedEvent,
    ExecutionDomainEventType.execution_reprioritized.value: ExecutionReprioritizedEvent,
}


def register_execution_event_types() -> None:
    for event_type, schema in EXECUTION_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_execution_created(
    producer: EventProducer | None,
    event: ExecutionCreatedEvent,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic="execution.events",
        key=str(event.execution_id),
        event_type=ExecutionDomainEventType.execution_created.value,
        payload=event.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.execution",
    )


async def publish_execution_status_changed(
    producer: EventProducer | None,
    event: ExecutionStatusChangedEvent,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic="execution.events",
        key=str(event.execution_id),
        event_type=ExecutionDomainEventType.execution_status_changed.value,
        payload=event.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.execution",
    )


async def publish_execution_reprioritized(
    producer: EventProducer | None,
    event: ExecutionReprioritizedEvent,
    correlation_ctx: CorrelationContext,
) -> None:
    if producer is None:
        return
    await producer.publish(
        topic="execution.events",
        key=str(event.execution_id),
        event_type=ExecutionDomainEventType.execution_reprioritized.value,
        payload=event.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.execution",
    )


async def workflow_runtime_consumer_handler(
    envelope: EventEnvelope, handler: Callable[[EventEnvelope], Awaitable[None]]
) -> None:
    await handler(envelope)


async def reasoning_budget_consumer_handler(
    envelope: EventEnvelope,
    handler: Callable[[EventEnvelope], Awaitable[None]],
) -> None:
    await handler(envelope)


async def fleet_health_consumer_handler(
    envelope: EventEnvelope,
    handler: Callable[[EventEnvelope], Awaitable[None]],
) -> None:
    await handler(envelope)


async def workspace_goal_consumer_handler(
    envelope: EventEnvelope,
    handler: Callable[[EventEnvelope], Awaitable[None]],
) -> None:
    await handler(envelope)


async def attention_consumer_handler(
    envelope: EventEnvelope,
    handler: Callable[[EventEnvelope], Awaitable[None]],
) -> None:
    await handler(envelope)


def register_execution_consumers(
    manager: EventConsumerManager,
    *,
    group_id: str,
    workflow_runtime_handler: Callable[[EventEnvelope], Awaitable[None]],
    reasoning_handler: Callable[[EventEnvelope], Awaitable[None]],
    fleet_handler: Callable[[EventEnvelope], Awaitable[None]],
    workspace_goal_handler: Callable[[EventEnvelope], Awaitable[None]],
    attention_handler: Callable[[EventEnvelope], Awaitable[None]],
) -> None:
    manager.subscribe("workflow.runtime", group_id, workflow_runtime_handler)
    manager.subscribe("runtime.reasoning", group_id, reasoning_handler)
    manager.subscribe("fleet.health", group_id, fleet_handler)
    manager.subscribe("workspace.goal", group_id, workspace_goal_handler)
    manager.subscribe("interaction.attention", group_id, attention_handler)
