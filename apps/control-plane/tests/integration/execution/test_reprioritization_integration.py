from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.execution.models import ExecutionEventType

import pytest

from tests.integration.execution.support import create_execution, create_workflow, create_workspace


@pytest.mark.asyncio
async def test_reprioritization_trigger_promotes_urgent_execution_via_scheduler(
    workflow_execution_stack,
    workflow_execution_client,
) -> None:
    workspace_id = await create_workspace(workflow_execution_stack)
    workflow_execution_stack.current_user["roles"] = [{"role": "workspace_admin"}]
    urgent_workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Urgent workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: urgent_step
    step_type: agent_task
    agent_fqn: ops.urgent
""",
    )
    relaxed_workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Relaxed workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: relaxed_step
    step_type: agent_task
    agent_fqn: ops.relaxed
""",
    )
    created = await workflow_execution_client.post(
        "/api/v1/reprioritization-triggers",
        json={
            "workspace_id": str(workspace_id),
            "name": "SLA 15%",
            "trigger_type": "sla_approach",
            "condition_config": {"threshold_fraction": 0.15},
            "action": "promote_to_front",
            "priority_rank": 10,
            "enabled": True,
        },
    )
    assert created.status_code == 201
    trigger_id = created.json()["id"]

    relaxed_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=relaxed_workflow_id,
        workspace_id=workspace_id,
        sla_deadline=datetime.now(UTC) + timedelta(minutes=30),
    )
    urgent_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=urgent_workflow_id,
        workspace_id=workspace_id,
        sla_deadline=datetime.now(UTC) + timedelta(minutes=1),
    )
    urgent = await workflow_execution_stack.execution_repository.get_execution_by_id(
        urgent_execution_id
    )
    relaxed = await workflow_execution_stack.execution_repository.get_execution_by_id(
        relaxed_execution_id
    )
    assert urgent is not None
    assert relaxed is not None
    relaxed.created_at = datetime.now(UTC) - timedelta(minutes=10)
    urgent.created_at = datetime.now(UTC) - timedelta(minutes=6)
    await workflow_execution_stack.session.flush()

    await workflow_execution_stack.scheduler_service.tick()

    dispatches = [
        call.args[0]["execution_id"]
        for call in workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list
    ]
    assert dispatches[:2] == [str(urgent_execution_id), str(relaxed_execution_id)]
    journal = await workflow_execution_stack.execution_service.get_journal(urgent_execution_id)
    reprioritized = [
        item
        for item in journal.items
        if item.event_type == ExecutionEventType.reprioritized
        and item.payload.get("trigger_id") == trigger_id
    ]
    assert len(reprioritized) == 1
    assert reprioritized[0].payload["trigger_name"] == "SLA 15%"
    assert reprioritized[0].payload["new_queue_order"][0]["execution_id"] == str(
        urgent_execution_id
    )


@pytest.mark.asyncio
async def test_reprioritization_is_idempotent_and_validates_trigger_input(
    workflow_execution_stack,
    workflow_execution_client,
) -> None:
    workspace_id = await create_workspace(workflow_execution_stack)
    workflow_execution_stack.current_user["roles"] = [{"role": "workspace_admin"}]
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Stable workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: only_step
    step_type: agent_task
    agent_fqn: ops.stable
""",
    )

    invalid = await workflow_execution_client.post(
        "/api/v1/reprioritization-triggers",
        json={
            "workspace_id": str(workspace_id),
            "name": "invalid",
            "trigger_type": "sla_approach",
            "condition_config": {"threshold_fraction": 2.0},
            "action": "promote_to_front",
            "priority_rank": 10,
            "enabled": True,
        },
    )
    assert invalid.status_code == 422

    created = await workflow_execution_client.post(
        "/api/v1/reprioritization-triggers",
        json={
            "workspace_id": str(workspace_id),
            "name": "SLA 20%",
            "trigger_type": "sla_approach",
            "condition_config": {"threshold_fraction": 0.2},
            "action": "promote_to_front",
            "priority_rank": 10,
            "enabled": True,
        },
    )
    assert created.status_code == 201

    urgent_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        sla_deadline=datetime.now(UTC) + timedelta(minutes=1),
    )
    relaxed_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        sla_deadline=datetime.now(UTC) + timedelta(minutes=20),
    )
    urgent = await workflow_execution_stack.execution_repository.get_execution_by_id(
        urgent_execution_id
    )
    relaxed = await workflow_execution_stack.execution_repository.get_execution_by_id(
        relaxed_execution_id
    )
    assert urgent is not None
    assert relaxed is not None
    urgent.created_at = datetime.now(UTC) - timedelta(minutes=6)
    relaxed.created_at = datetime.now(UTC) - timedelta(minutes=5)
    await workflow_execution_stack.session.flush()

    await workflow_execution_stack.scheduler_service.tick()

    urgent_journal = await workflow_execution_stack.execution_service.get_journal(
        urgent_execution_id
    )
    relaxed_journal = await workflow_execution_stack.execution_service.get_journal(
        relaxed_execution_id
    )
    assert [
        item
        for item in urgent_journal.items
        if item.event_type == ExecutionEventType.reprioritized
        and item.payload.get("trigger_id") is not None
    ] == []
    assert [
        item
        for item in relaxed_journal.items
        if item.event_type == ExecutionEventType.reprioritized
        and item.payload.get("trigger_id") is not None
    ] == []


@pytest.mark.asyncio
async def test_reprioritization_budget_and_priority_conflicts_are_handled(
    workflow_execution_stack,
    workflow_execution_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = await create_workspace(workflow_execution_stack)
    workflow_execution_stack.current_user["roles"] = [{"role": "workspace_admin"}]
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Conflict workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: conflict_step
    step_type: agent_task
    agent_fqn: ops.conflict
""",
    )
    low = await workflow_execution_client.post(
        "/api/v1/reprioritization-triggers",
        json={
            "workspace_id": str(workspace_id),
            "name": "low",
            "trigger_type": "sla_approach",
            "condition_config": {"threshold_fraction": 0.5},
            "action": "promote_to_front",
            "priority_rank": 50,
            "enabled": True,
        },
    )
    high = await workflow_execution_client.post(
        "/api/v1/reprioritization-triggers",
        json={
            "workspace_id": str(workspace_id),
            "name": "high",
            "trigger_type": "sla_approach",
            "condition_config": {"threshold_fraction": 0.5},
            "action": "promote_to_front",
            "priority_rank": 1,
            "enabled": True,
        },
    )
    assert low.status_code == 201
    assert high.status_code == 201

    relaxed_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        sla_deadline=datetime.now(UTC) + timedelta(minutes=15),
    )
    urgent_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        sla_deadline=datetime.now(UTC) + timedelta(minutes=1),
    )
    urgent = await workflow_execution_stack.execution_repository.get_execution_by_id(
        urgent_execution_id
    )
    relaxed = await workflow_execution_stack.execution_repository.get_execution_by_id(
        relaxed_execution_id
    )
    assert urgent is not None
    assert relaxed is not None
    relaxed.created_at = datetime.now(UTC) - timedelta(minutes=10)
    urgent.created_at = datetime.now(UTC) - timedelta(minutes=6)
    await workflow_execution_stack.session.flush()

    values = iter([0.0, 1.0])
    monkeypatch.setattr("platform.execution.reprioritization.monotonic", lambda: next(values))
    result = await workflow_execution_stack.reprioritization_service.evaluate_for_dispatch_cycle(
        [relaxed, urgent],
        workspace_id,
        cycle_budget_ms=0,
    )
    assert result.timed_out is True
    assert [item.id for item in result.ordered_executions] == [relaxed.id, urgent.id]

    monkeypatch.undo()
    await workflow_execution_stack.scheduler_service.tick()
    journal = await workflow_execution_stack.execution_service.get_journal(urgent_execution_id)
    reprioritized = [
        item
        for item in journal.items
        if item.event_type == ExecutionEventType.reprioritized
        and item.payload.get("trigger_id") is not None
    ]
    assert len(reprioritized) == 1
    assert reprioritized[0].payload["trigger_name"] == "high"
