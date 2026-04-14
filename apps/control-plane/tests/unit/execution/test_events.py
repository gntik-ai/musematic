from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext, make_envelope
from platform.common.events.registry import event_registry
from platform.execution.events import (
    ExecutionCreatedEvent,
    ExecutionDomainEventType,
    ExecutionReprioritizedEvent,
    ExecutionStatusChangedEvent,
    _coerce_uuid,
    _find_active_execution_ids,
    attention_consumer_handler,
    event_bus_consumer_handler,
    fire_cron_trigger,
    fleet_health_consumer_handler,
    publish_execution_created,
    publish_execution_reprioritized,
    publish_execution_status_changed,
    reasoning_budget_consumer_handler,
    register_execution_consumers,
    register_execution_event_types,
    workflow_runtime_consumer_handler,
    workspace_goal_consumer_handler,
)
from platform.execution.models import ExecutionEventType
from platform.execution.schemas import ExecutionCreate
from platform.workflows.models import TriggerType
from platform.workflows.schemas import TriggerCreate, WorkflowCreate
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from tests.unit.execution.test_scheduler import _build_scheduler
from tests.workflow_execution_support import FakeProducer


@pytest.mark.asyncio
async def test_execution_publishers_and_registry_cover_domain_events() -> None:
    producer = FakeProducer()
    correlation = CorrelationContext(workspace_id=uuid4(), correlation_id=uuid4())
    execution_id = uuid4()
    register_execution_event_types()

    await publish_execution_created(
        producer,
        ExecutionCreatedEvent(
            execution_id=execution_id,
            workflow_definition_id=uuid4(),
            workflow_version_id=uuid4(),
            workspace_id=uuid4(),
        ),
        correlation,
    )
    await publish_execution_status_changed(
        producer,
        ExecutionStatusChangedEvent(
            execution_id=execution_id,
            status="running",
            step_id="step_a",
        ),
        correlation,
    )
    await publish_execution_reprioritized(
        producer,
        ExecutionReprioritizedEvent(
            execution_id=execution_id,
            trigger_reason="budget_threshold_breached",
            steps_affected=["step_a"],
        ),
        correlation,
    )

    assert event_registry.is_registered(ExecutionDomainEventType.execution_created.value) is True
    assert (
        event_registry.is_registered(ExecutionDomainEventType.execution_status_changed.value)
        is True
    )
    assert (
        event_registry.is_registered(ExecutionDomainEventType.execution_reprioritized.value)
        is True
    )
    assert [message["event_type"] for message in producer.messages] == [
        ExecutionDomainEventType.execution_created.value,
        ExecutionDomainEventType.execution_status_changed.value,
        ExecutionDomainEventType.execution_reprioritized.value,
    ]


@pytest.mark.asyncio
async def test_execution_event_publishers_ignore_missing_producer() -> None:
    correlation = CorrelationContext(workspace_id=uuid4(), correlation_id=uuid4())

    await publish_execution_created(
        None,
        ExecutionCreatedEvent(
            execution_id=uuid4(),
            workflow_definition_id=uuid4(),
            workflow_version_id=uuid4(),
            workspace_id=uuid4(),
        ),
        correlation,
    )
    await publish_execution_status_changed(
        None,
        ExecutionStatusChangedEvent(execution_id=uuid4(), status="queued"),
        correlation,
    )
    await publish_execution_reprioritized(
        None,
        ExecutionReprioritizedEvent(
            execution_id=uuid4(),
            trigger_reason="external_event",
            steps_affected=[],
        ),
        correlation,
    )


@pytest.mark.asyncio
async def test_execution_event_handlers_cover_proxy_and_non_matching_paths() -> None:
    handler = AsyncMock()
    envelope = make_envelope("custom.event", "tests", {})

    await workflow_runtime_consumer_handler(envelope, handler)
    assert handler.await_count == 1

    assert await reasoning_budget_consumer_handler(envelope) == []
    assert await fleet_health_consumer_handler(envelope) == []
    assert await workspace_goal_consumer_handler(envelope) == []
    assert await attention_consumer_handler(envelope) == []
    assert await event_bus_consumer_handler(
        make_envelope("event", "tests", {}),
        workflow_service=SimpleNamespace(repository=AsyncMock()),
        execution_service=SimpleNamespace(),
    ) == []


@pytest.mark.asyncio
async def test_execution_event_handlers_drive_trigger_and_reprioritization_logic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    workflow_repository = workflow_service.repository
    actor_id = uuid4()
    workspace_id = uuid4()
    fleet_id = uuid4()
    interaction_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Event Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
  - id: step_b
    step_type: tool_call
    tool_fqn: ns:tool
            """.strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    cron_trigger = await workflow_service.create_trigger(
        workflow.id,
        TriggerCreate(
            trigger_type=TriggerType.cron,
            name="cron",
            config={"cron_expression": "0 5 * * *"},
        ),
    )
    await workflow_service.create_trigger(
        workflow.id,
        TriggerCreate(
            trigger_type=TriggerType.workspace_goal,
            name="goal",
            config={"workspace_id": str(workspace_id), "goal_type_pattern": "analyze-*"},
        ),
    )
    await workflow_service.create_trigger(
        workflow.id,
        TriggerCreate(
            trigger_type=TriggerType.event_bus,
            name="bus",
            config={"topic": "connector.ingress", "event_type_pattern": "order.*"},
        ),
    )

    execution = await execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow.id,
            workspace_id=workspace_id,
            correlation_fleet_id=fleet_id,
            correlation_interaction_id=interaction_id,
            sla_deadline=datetime.now(UTC),
        ),
        created_by=actor_id,
    )
    async def _fake_find_active_execution_ids(*args, **kwargs):
        del args, kwargs
        return [execution.id]

    monkeypatch.setattr(
        "platform.execution.events._find_active_execution_ids",
        _fake_find_active_execution_ids,
    )
    await execution_service.record_runtime_event(
        execution.id,
        step_id="step_a",
        event_type=ExecutionEventType.dispatched,
        payload={"step_type": "agent_task"},
    )

    cron_execution_id = await fire_cron_trigger(
        cron_trigger.id,
        workflow_service=workflow_service,
        execution_service=execution_service,
    )
    goal_ids = await workspace_goal_consumer_handler(
        make_envelope(
            "goal.created",
            "workspace.goal",
            {
                "workspace_id": str(workspace_id),
                "goal_id": str(uuid4()),
                "goal_type": "analyze-quarterly",
            },
        ),
        workflow_service=workflow_service,
        execution_service=execution_service,
    )
    bus_ids = await event_bus_consumer_handler(
        make_envelope(
            "order.created",
            "event.bus",
            {"topic": "connector.ingress", "event_type": "order.created"},
        ),
        workflow_service=workflow_service,
        execution_service=execution_service,
    )
    budget_ids = await reasoning_budget_consumer_handler(
        make_envelope(
            "budget.threshold_breached",
            "runtime.reasoning",
            {"execution_id": str(execution.id), "event_type": "budget.threshold_breached"},
        ),
        scheduler_service=scheduler,
    )
    fleet_ids = await fleet_health_consumer_handler(
        make_envelope(
            "member.failed",
            "fleet.health",
            {
                "fleet_id": str(fleet_id),
                "event_type": "member.failed",
            },
        ),
        scheduler_service=scheduler,
    )
    attention_ids = await attention_consumer_handler(
        make_envelope(
            "attention.requested",
            "interaction.attention",
            {"interaction_id": str(interaction_id)},
        ),
        scheduler_service=scheduler,
    )

    assert cron_execution_id in execution_service.repository.executions
    assert len(goal_ids) == 1
    assert len(bus_ids) == 1
    assert budget_ids == [execution.id]
    assert fleet_ids == [execution.id]
    assert attention_ids == [execution.id]
    assert workflow_repository.triggers[cron_trigger.id].last_fired_at is not None


@pytest.mark.asyncio
async def test_execution_event_helpers_cover_fallbacks_registration_and_filters() -> None:
    handler = AsyncMock()
    envelope = make_envelope(
        "budget.threshold_breached",
        "runtime.reasoning",
        {},
    )

    assert await reasoning_budget_consumer_handler(envelope, handler=handler) == []
    assert await fleet_health_consumer_handler(envelope, handler=handler) == []
    assert await workspace_goal_consumer_handler(envelope, handler=handler) == []
    assert await attention_consumer_handler(envelope, handler=handler) == []
    assert handler.await_count == 4

    manager = SimpleNamespace(subscribe=Mock())
    noop_handler = AsyncMock()
    register_execution_consumers(
        manager,
        group_id="workflow-execution",
        workflow_runtime_handler=noop_handler,
        reasoning_handler=noop_handler,
        fleet_handler=noop_handler,
        workspace_goal_handler=noop_handler,
        attention_handler=noop_handler,
        event_bus_handler=noop_handler,
    )

    topics = [call.args[0] for call in manager.subscribe.call_args_list]
    assert topics == [
        "workflow.runtime",
        "runtime.reasoning",
        "fleet.health",
        "workspace.goal",
        "interaction.attention",
        "event.bus",
    ]


@pytest.mark.asyncio
async def test_execution_event_helpers_cover_empty_identifier_paths_and_unknown_triggers() -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()

    assert await reasoning_budget_consumer_handler(
        make_envelope("budget.threshold_breached", "runtime.reasoning", {}),
        scheduler_service=scheduler,
    ) == []
    assert await fleet_health_consumer_handler(
        make_envelope("member.failed", "fleet.health", {}),
        scheduler_service=scheduler,
    ) == []
    assert await workspace_goal_consumer_handler(
        make_envelope("goal.created", "workspace.goal", {"goal_type": "ops"}),
        workflow_service=workflow_service,
        execution_service=execution_service,
    ) == []
    assert await attention_consumer_handler(
        make_envelope("attention.requested", "interaction.attention", {}),
        scheduler_service=scheduler,
    ) == []
    with pytest.raises(ValueError, match="Unknown trigger"):
        await fire_cron_trigger(
            uuid4(),
            workflow_service=workflow_service,
            execution_service=execution_service,
        )


@pytest.mark.asyncio
async def test_execution_event_helpers_cover_direct_uuid_coercion_and_query_helpers() -> None:
    execution_id = uuid4()
    interaction_id = uuid4()
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(all=lambda: [(execution_id,), (interaction_id,)])
        )
    )

    resolved = await _find_active_execution_ids(
        session,
        fleet_id=uuid4(),
        interaction_id=interaction_id,
    )

    assert _coerce_uuid(None) is None
    assert _coerce_uuid(execution_id) == execution_id
    assert _coerce_uuid(str(execution_id)) == execution_id
    assert resolved == [execution_id, interaction_id]
