from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.events.envelope import make_envelope
from platform.execution.events import (
    fleet_health_consumer_handler,
    reasoning_budget_consumer_handler,
)
from platform.execution.models import ExecutionEventType
from uuid import uuid4

import pytest

from tests.integration.execution.support import create_execution, create_workflow


@pytest.mark.asyncio
async def test_reprioritization_consumers_append_events_and_skip_active_steps(
    workflow_execution_stack,
) -> None:
    workspace_id = uuid4()
    fleet_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Reprioritization Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
  - id: step_b
    step_type: tool_call
    tool_fqn: ops.enrich
        """,
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        correlation_fleet_id=fleet_id,
    )
    await workflow_execution_stack.execution_service.record_runtime_event(
        execution_id,
        step_id="step_a",
        event_type=ExecutionEventType.dispatched,
        payload={"step_type": "agent_task"},
    )

    affected_by_budget = await reasoning_budget_consumer_handler(
        make_envelope(
            "budget.threshold_breached",
            "runtime.reasoning",
            {"execution_id": str(execution_id), "event_type": "budget.threshold_breached"},
        ),
        scheduler_service=workflow_execution_stack.scheduler_service,
    )
    affected_by_fleet = await fleet_health_consumer_handler(
        make_envelope(
            "member.failed",
            "fleet.health",
            {"fleet_id": str(fleet_id), "event_type": "member.failed"},
        ),
        scheduler_service=workflow_execution_stack.scheduler_service,
    )

    journal = await workflow_execution_stack.execution_service.get_journal(execution_id)
    reprioritized_events = [
        item for item in journal.items if item.event_type == ExecutionEventType.reprioritized
    ]

    assert affected_by_budget == [execution_id]
    assert affected_by_fleet == [execution_id]
    assert len(reprioritized_events) == 2
    assert reprioritized_events[0].payload["trigger_reason"] == "budget_threshold_breached"
    assert reprioritized_events[1].payload["trigger_reason"] == "resource_constraint_changed"
    assert reprioritized_events[0].payload["steps_affected"] == ["step_b"]
    assert "step_a" not in reprioritized_events[0].payload["steps_affected"]
    assert any(
        message["event_type"] == "execution.reprioritized"
        for message in workflow_execution_stack.kafka_mock.messages
    )


@pytest.mark.asyncio
async def test_scheduler_tick_triggers_sla_reprioritization_when_window_is_mostly_consumed(
    workflow_execution_stack,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="SLA Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: approval_step
    step_type: approval_gate
    approval_config:
      required_approvers: [ops]
      timeout_seconds: 300
      timeout_action: fail
  - id: work_step
    step_type: tool_call
    tool_fqn: ops.enrich
        """,
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        sla_deadline=datetime.now(UTC) + timedelta(minutes=1),
    )
    execution = await workflow_execution_stack.execution_repository.get_execution_by_id(
        execution_id
    )
    assert execution is not None
    execution.created_at = datetime.now(UTC) - timedelta(minutes=9)
    await workflow_execution_stack.session.flush()

    await workflow_execution_stack.scheduler_service.tick()

    journal = await workflow_execution_stack.execution_service.get_journal(execution_id)
    reprioritized_events = [
        item for item in journal.items if item.event_type == ExecutionEventType.reprioritized
    ]

    assert len(reprioritized_events) == 1
    assert reprioritized_events[0].payload["trigger_reason"] == "sla_deadline_approaching"
    assert reprioritized_events[0].payload["steps_affected"][0] == "approval_step"
