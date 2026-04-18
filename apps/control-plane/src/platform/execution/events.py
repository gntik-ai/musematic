from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from fnmatch import fnmatch
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from platform.execution.models import Execution, ExecutionStatus
from platform.execution.schemas import ExecutionCreate
from platform.workflows.models import TriggerType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select

if TYPE_CHECKING:
    from platform.execution.scheduler import SchedulerService
    from platform.execution.service import ExecutionService
    from platform.workflows.service import WorkflowService


ACTIVE_EXECUTION_STATUSES: Final[tuple[ExecutionStatus, ...]] = (
    ExecutionStatus.queued,
    ExecutionStatus.running,
    ExecutionStatus.waiting_for_approval,
    ExecutionStatus.compensating,
)


class ExecutionDomainEventType(StrEnum):
    """Represent the execution domain event type."""
    execution_created = "execution.created"
    execution_status_changed = "execution.status_changed"
    execution_reprioritized = "execution.reprioritized"
    prompt_secret_detected = "prompt_secret_detected"


class ExecutionCreatedEvent(BaseModel):
    """Represent the execution created event payload."""
    execution_id: UUID
    workflow_definition_id: UUID
    workflow_version_id: UUID
    workspace_id: UUID


class ExecutionStatusChangedEvent(BaseModel):
    """Represent the execution status changed event payload."""
    execution_id: UUID
    status: str
    step_id: str | None = None


class ExecutionReprioritizedEvent(BaseModel):
    """Represent the execution reprioritized event payload."""
    execution_id: UUID
    trigger_reason: str
    steps_affected: list[str]


class PromptSecretDetectedEvent(BaseModel):
    """Represent the prompt secret detected event payload."""
    execution_id: UUID
    workspace_id: UUID
    agent_fqn: str
    step_id: str
    secret_type: str


EXECUTION_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    ExecutionDomainEventType.execution_created.value: ExecutionCreatedEvent,
    ExecutionDomainEventType.execution_status_changed.value: ExecutionStatusChangedEvent,
    ExecutionDomainEventType.execution_reprioritized.value: ExecutionReprioritizedEvent,
    ExecutionDomainEventType.prompt_secret_detected.value: PromptSecretDetectedEvent,
}


def register_execution_event_types() -> None:
    """Register execution event types."""
    for event_type, schema in EXECUTION_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


async def publish_execution_created(
    producer: EventProducer | None,
    event: ExecutionCreatedEvent,
    correlation_ctx: CorrelationContext,
) -> None:
    """Publish execution created."""
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
    """Publish execution status changed."""
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
    """Publish execution reprioritized."""
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


async def publish_prompt_secret_detected(
    producer: EventProducer | None,
    event: PromptSecretDetectedEvent,
    correlation_ctx: CorrelationContext,
) -> None:
    """Publish prompt secret detection alert."""
    if producer is None:
        return
    await producer.publish(
        topic="monitor.alerts",
        key=str(event.execution_id),
        event_type=ExecutionDomainEventType.prompt_secret_detected.value,
        payload=event.model_dump(mode="json"),
        correlation_ctx=correlation_ctx,
        source="platform.execution",
    )


async def workflow_runtime_consumer_handler(
    envelope: EventEnvelope,
    handler: Callable[[EventEnvelope], Awaitable[None]] | None = None,
) -> None:
    """Handle workflow runtime consumer handler."""
    if handler is not None:
        await handler(envelope)


async def reasoning_budget_consumer_handler(
    envelope: EventEnvelope,
    handler: Callable[[EventEnvelope], Awaitable[None]] | None = None,
    *,
    scheduler_service: SchedulerService | None = None,
) -> list[UUID]:
    """Handle reasoning budget consumer handler."""
    if handler is not None and scheduler_service is None:
        await handler(envelope)
        return []

    if scheduler_service is None:
        return []

    if envelope.event_type != "budget.threshold_breached" and envelope.payload.get(
        "event_type"
    ) != "budget.threshold_breached":
        return []

    execution_id = _coerce_uuid(envelope.payload.get("execution_id"))
    if execution_id is None:
        execution_id = envelope.correlation_context.execution_id
    if execution_id is None:
        return []

    await scheduler_service.handle_reprioritization_trigger(
        "budget_threshold_breached",
        execution_id,
    )
    return [execution_id]


async def fleet_health_consumer_handler(
    envelope: EventEnvelope,
    handler: Callable[[EventEnvelope], Awaitable[None]] | None = None,
    *,
    scheduler_service: SchedulerService | None = None,
) -> list[UUID]:
    """Handle fleet health consumer handler."""
    if handler is not None and scheduler_service is None:
        await handler(envelope)
        return []

    if scheduler_service is None:
        return []

    reported_event_type = str(envelope.payload.get("event_type", envelope.event_type))
    if reported_event_type not in {"member.failed", "fleet.health.updated"}:
        return []

    fleet_id = _coerce_uuid(envelope.payload.get("fleet_id"))
    if fleet_id is None:
        fleet_id = envelope.correlation_context.fleet_id
    if fleet_id is None:
        return []

    execution_ids = await _find_active_execution_ids(
        scheduler_service.repository.session,
        fleet_id=fleet_id,
    )
    for execution_id in execution_ids:
        await scheduler_service.handle_reprioritization_trigger(
            "resource_constraint_changed",
            execution_id,
        )
    return execution_ids


async def workspace_goal_consumer_handler(
    envelope: EventEnvelope,
    handler: Callable[[EventEnvelope], Awaitable[None]] | None = None,
    *,
    workflow_service: WorkflowService | None = None,
    execution_service: ExecutionService | None = None,
) -> list[UUID]:
    """Handle workspace goal consumer handler."""
    if handler is not None and workflow_service is None and execution_service is None:
        await handler(envelope)
        return []

    if workflow_service is None or execution_service is None:
        return []

    workspace_id = _coerce_uuid(envelope.payload.get("workspace_id"))
    if workspace_id is None:
        workspace_id = envelope.correlation_context.workspace_id
    if workspace_id is None:
        return []

    goal_id = _coerce_uuid(envelope.payload.get("goal_id"))
    if goal_id is None:
        goal_id = envelope.correlation_context.goal_id
    goal_type = str(envelope.payload.get("goal_type", ""))

    created_execution_ids: list[UUID] = []
    triggers = await workflow_service.repository.list_active_triggers_by_type(
        TriggerType.workspace_goal
    )
    for trigger in triggers:
        configured_workspace = str(trigger.config.get("workspace_id", workspace_id))
        pattern = str(trigger.config.get("goal_type_pattern", "*"))
        if configured_workspace != str(workspace_id):
            continue
        if not fnmatch(goal_type, pattern):
            continue
        workflow = await workflow_service.get_workflow(trigger.definition_id)
        execution = await execution_service.create_execution(
            ExecutionCreate(
                workflow_definition_id=workflow.id,
                trigger_type=TriggerType.workspace_goal,
                trigger_id=trigger.id,
                input_parameters=dict(envelope.payload),
                workspace_id=workflow.workspace_id,
                correlation_goal_id=goal_id,
            )
        )
        await workflow_service.record_trigger_fired(trigger.id, execution_id=execution.id)
        created_execution_ids.append(execution.id)
    return created_execution_ids


async def attention_consumer_handler(
    envelope: EventEnvelope,
    handler: Callable[[EventEnvelope], Awaitable[None]] | None = None,
    *,
    scheduler_service: SchedulerService | None = None,
) -> list[UUID]:
    """Handle attention consumer handler."""
    if handler is not None and scheduler_service is None:
        await handler(envelope)
        return []

    if scheduler_service is None:
        return []

    execution_id = _coerce_uuid(envelope.payload.get("execution_id"))
    if execution_id is None:
        execution_id = envelope.correlation_context.execution_id
    execution_ids = [execution_id] if execution_id is not None else []

    if not execution_ids:
        interaction_id = _coerce_uuid(envelope.payload.get("interaction_id"))
        if interaction_id is None:
            interaction_id = envelope.correlation_context.interaction_id
        if interaction_id is None:
            return []
        execution_ids = await _find_active_execution_ids(
            scheduler_service.repository.session,
            interaction_id=interaction_id,
        )

    for current_execution_id in execution_ids:
        await scheduler_service.handle_reprioritization_trigger(
            "external_event",
            current_execution_id,
        )
    return execution_ids


async def fire_cron_trigger(
    trigger_id: UUID,
    *,
    workflow_service: WorkflowService,
    execution_service: ExecutionService,
) -> UUID:
    """Fire cron trigger."""
    trigger = await workflow_service.repository.get_trigger_by_id(trigger_id)
    if trigger is None:
        raise ValueError(f"Unknown trigger: {trigger_id}")
    workflow = await workflow_service.get_workflow(trigger.definition_id)
    execution = await execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow.id,
            trigger_type=TriggerType.cron,
            trigger_id=trigger.id,
            input_parameters={},
            workspace_id=workflow.workspace_id,
        )
    )
    await workflow_service.record_trigger_fired(trigger.id, execution_id=execution.id)
    return execution.id


async def event_bus_consumer_handler(
    envelope: EventEnvelope,
    *,
    workflow_service: WorkflowService,
    execution_service: ExecutionService,
) -> list[UUID]:
    """Handle event bus consumer handler."""
    topic = str(envelope.payload.get("topic", ""))
    event_type = str(envelope.payload.get("event_type", envelope.event_type))
    if not topic:
        return []

    created_execution_ids: list[UUID] = []
    triggers = await workflow_service.repository.list_active_triggers_by_type(TriggerType.event_bus)
    for trigger in triggers:
        configured_topic = str(trigger.config.get("topic", ""))
        configured_event_type = str(trigger.config.get("event_type_pattern", "*"))
        if configured_topic and not fnmatch(topic, configured_topic):
            continue
        if configured_event_type and not fnmatch(event_type, configured_event_type):
            continue
        workflow = await workflow_service.get_workflow(trigger.definition_id)
        execution = await execution_service.create_execution(
            ExecutionCreate(
                workflow_definition_id=workflow.id,
                trigger_type=TriggerType.event_bus,
                trigger_id=trigger.id,
                input_parameters=dict(envelope.payload),
                workspace_id=workflow.workspace_id,
            )
        )
        await workflow_service.record_trigger_fired(trigger.id, execution_id=execution.id)
        created_execution_ids.append(execution.id)
    return created_execution_ids


def register_execution_consumers(
    manager: EventConsumerManager,
    *,
    group_id: str,
    workflow_runtime_handler: Callable[[EventEnvelope], Awaitable[None]],
    reasoning_handler: Callable[[EventEnvelope], Awaitable[None]],
    fleet_handler: Callable[[EventEnvelope], Awaitable[None]],
    workspace_goal_handler: Callable[[EventEnvelope], Awaitable[None]],
    attention_handler: Callable[[EventEnvelope], Awaitable[None]],
    event_bus_handler: Callable[[EventEnvelope], Awaitable[None]] | None = None,
) -> None:
    """Register execution consumers."""
    manager.subscribe("workflow.runtime", group_id, workflow_runtime_handler)
    manager.subscribe("runtime.reasoning", group_id, reasoning_handler)
    manager.subscribe("fleet.health", group_id, fleet_handler)
    manager.subscribe("workspace.goal", group_id, workspace_goal_handler)
    manager.subscribe("interaction.attention", group_id, attention_handler)
    if event_bus_handler is not None:
        manager.subscribe("event.bus", group_id, event_bus_handler)


def _coerce_uuid(value: object | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


async def _find_active_execution_ids(
    session: Any,
    *,
    fleet_id: UUID | None = None,
    interaction_id: UUID | None = None,
) -> list[UUID]:
    query = select(Execution.id).where(Execution.status.in_(ACTIVE_EXECUTION_STATUSES))
    if fleet_id is not None:
        query = query.where(Execution.correlation_fleet_id == fleet_id)
    if interaction_id is not None:
        query = query.where(Execution.correlation_interaction_id == interaction_id)
    result = await session.execute(query)
    return [row[0] for row in result.all()]
