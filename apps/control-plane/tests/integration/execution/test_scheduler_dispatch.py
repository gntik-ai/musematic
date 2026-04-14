from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.execution.models import ExecutionEventType
from platform.execution.schemas import ApprovalDecisionRequest
from uuid import UUID, uuid4

import pytest

from tests.integration.execution.support import (
    create_execution,
    create_workflow,
    mark_step_completed,
)


@pytest.mark.asyncio
async def test_scheduler_dispatches_in_dependency_order_and_retries_expired_leases(
    workflow_execution_stack,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Dispatch Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
  - id: step_b
    step_type: tool_call
    tool_fqn: ops.enrich
    depends_on: [step_a]
        """,
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
    )

    await workflow_execution_stack.scheduler_service.tick()

    assert [
        call.args[0]["step_id"]
        for call in workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list
    ] == ["step_a"]

    redis_client = await workflow_execution_stack.scheduler_service.redis_client._get_client()
    lease_key = f"exec:lease:{execution_id}:step_a"
    assert await redis_client.exists(lease_key) == 1

    await workflow_execution_stack.scheduler_service.tick()
    assert (
        len(workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list) == 1
    )

    lease = await workflow_execution_stack.execution_repository.get_active_dispatch_lease(
        execution_id,
        "step_a",
    )
    assert lease is not None
    lease.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await workflow_execution_stack.session.flush()
    await redis_client.delete(lease_key)

    await workflow_execution_stack.scheduler_service.tick()
    retried_calls = [
        call.args[0]["step_id"]
        for call in workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list
    ]
    assert retried_calls == ["step_a", "step_a"]

    journal = await workflow_execution_stack.execution_service.get_journal(execution_id)
    assert any(item.event_type == ExecutionEventType.retried for item in journal.items)

    await mark_step_completed(
        workflow_execution_stack,
        execution_id=execution_id,
        step_id="step_a",
        payload={"output": {"value": "A"}},
    )
    await workflow_execution_stack.scheduler_service.tick()

    final_calls = [
        call.args[0]["step_id"]
        for call in workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list
    ]
    assert final_calls[-1] == "step_b"


@pytest.mark.asyncio
async def test_scheduler_prioritizes_near_sla_executions_first(
    workflow_execution_stack,
) -> None:
    workspace_id = uuid4()
    relaxed_workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Relaxed Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
        """,
    )
    urgent_workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Urgent Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: step_b
    step_type: agent_task
    agent_fqn: ops.fetch
        """,
    )

    await create_execution(
        workflow_execution_stack,
        workflow_id=relaxed_workflow_id,
        workspace_id=workspace_id,
        sla_deadline=datetime.now(UTC) + timedelta(hours=1),
    )
    await create_execution(
        workflow_execution_stack,
        workflow_id=urgent_workflow_id,
        workspace_id=workspace_id,
        sla_deadline=datetime.now(UTC) + timedelta(minutes=5),
    )

    await workflow_execution_stack.scheduler_service.tick()

    dispatch_order = [
        call.args[0]["step_id"]
        for call in workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list
    ]
    assert dispatch_order[:2] == ["step_b", "step_a"]


@pytest.mark.asyncio
async def test_scheduler_handles_approval_gate_end_to_end(
    workflow_execution_stack,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Approval Dispatch Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
  - id: approval_step
    step_type: approval_gate
    depends_on: [step_a]
    approval_config:
      required_approvers: [ops]
      timeout_seconds: 300
      timeout_action: fail
  - id: step_c
    step_type: tool_call
    tool_fqn: ops.publish
    depends_on: [approval_step]
        """,
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
    )

    await workflow_execution_stack.scheduler_service.tick()
    await mark_step_completed(
        workflow_execution_stack,
        execution_id=execution_id,
        step_id="step_a",
        payload={"output": {"value": "A"}},
    )

    workflow_execution_stack.runtime_controller_stub.dispatch.reset_mock()
    await workflow_execution_stack.scheduler_service.tick()

    approval_wait = await workflow_execution_stack.execution_repository.get_approval_wait(
        execution_id,
        "approval_step",
    )
    journal = await workflow_execution_stack.execution_service.get_journal(execution_id)

    assert approval_wait is not None
    assert workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list == []
    assert any(
        item.event_type == ExecutionEventType.waiting_for_approval for item in journal.items
    )

    await workflow_execution_stack.execution_service.record_approval_decision(
        execution_id,
        "approval_step",
        request=ApprovalDecisionRequest(decision="approved", comment="ok"),
        decided_by=UUID(workflow_execution_stack.current_user["sub"]),
    )
    await workflow_execution_stack.scheduler_service.tick()

    dispatched_steps = [
        call.args[0]["step_id"]
        for call in workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list
    ]
    assert dispatched_steps == ["step_c"]
