from __future__ import annotations

from datetime import UTC, datetime
from platform.execution.models import ExecutionEventType, ExecutionStatus
from uuid import uuid4

import pytest

from tests.integration.execution.support import (
    create_execution,
    create_workflow,
    mark_step_completed,
)


@pytest.mark.asyncio
async def test_default_checkpoint_policy_captures_before_tool_invocations(
    workflow_execution_stack,
    workflow_execution_client,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Checkpoint workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: tool_call
    tool_fqn: ops.one
  - id: step_b
    step_type: tool_call
    tool_fqn: ops.two
    depends_on: [step_a]
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
        payload={"output": {"value": "done"}},
    )
    await workflow_execution_stack.scheduler_service.tick()

    checkpoints = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/checkpoints"
    )
    detail = await workflow_execution_client.get(f"/api/v1/executions/{execution_id}/checkpoints/2")

    assert checkpoints.status_code == 200
    assert [item["checkpoint_number"] for item in checkpoints.json()["items"]] == [1, 2]
    assert detail.status_code == 200
    assert detail.json()["policy_snapshot"] == {"type": "before_tool_invocations"}
    assert detail.json()["pending_step_ids"] == ["step_b"]


@pytest.mark.asyncio
async def test_checkpoint_policy_disabled_and_null_backcompat_behave_as_expected(
    workflow_execution_stack,
    workflow_execution_client,
) -> None:
    workspace_id = uuid4()
    disabled_workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Disabled checkpoints",
        yaml_source="""
schema_version: 1
steps:
  - id: disabled_step
    step_type: tool_call
    tool_fqn: ops.disabled
""",
        checkpoint_policy={"type": "disabled"},
    )
    backcompat_workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Backcompat checkpoints",
        yaml_source="""
schema_version: 1
steps:
  - id: compat_step
    step_type: tool_call
    tool_fqn: ops.compat
""",
    )
    disabled_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=disabled_workflow_id,
        workspace_id=workspace_id,
    )
    backcompat_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=backcompat_workflow_id,
        workspace_id=workspace_id,
    )
    compat_execution = await workflow_execution_stack.execution_repository.get_execution_by_id(
        backcompat_execution_id
    )
    assert compat_execution is not None
    compat_execution.checkpoint_policy_snapshot = None
    await workflow_execution_stack.session.flush()

    await workflow_execution_stack.scheduler_service.tick()

    disabled = await workflow_execution_client.get(
        f"/api/v1/executions/{disabled_execution_id}/checkpoints"
    )
    compat = await workflow_execution_client.get(
        f"/api/v1/executions/{backcompat_execution_id}/checkpoints"
    )

    assert disabled.status_code == 200
    assert disabled.json()["items"] == []
    assert compat.status_code == 200
    assert len(compat.json()["items"]) == 1


@pytest.mark.asyncio
async def test_checkpoint_capture_failure_pauses_execution_without_dispatch(
    workflow_execution_stack,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Checkpoint failure",
        yaml_source="""
schema_version: 1
steps:
  - id: failing_step
    step_type: tool_call
    tool_fqn: ops.fail
""",
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
    )
    workflow_execution_stack.checkpoint_service.settings.checkpoint_max_size_bytes = 1

    await workflow_execution_stack.scheduler_service.tick()

    execution = await workflow_execution_stack.execution_repository.get_execution_by_id(
        execution_id
    )
    journal = await workflow_execution_stack.execution_service.get_journal(execution_id)
    assert execution is not None
    assert execution.status is ExecutionStatus.paused
    assert workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list == []
    assert journal.items[-1].payload["failure_kind"] == "checkpoint_capture"


@pytest.mark.asyncio
async def test_checkpoint_rollback_endpoint_restores_state_and_resume_uses_restored_queue(
    workflow_execution_stack,
    workflow_execution_client,
) -> None:
    workspace_id = uuid4()
    workflow_execution_stack.current_user["permissions"] = ["execution.rollback"]
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Rollback workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: tool_call
    tool_fqn: ops.a
  - id: step_b
    step_type: tool_call
    tool_fqn: ops.b
    depends_on: [step_a]
  - id: step_c
    step_type: tool_call
    tool_fqn: ops.c
    depends_on: [step_b]
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
        payload={"output": {"value": "a"}},
    )
    await workflow_execution_stack.scheduler_service.tick()
    await mark_step_completed(
        workflow_execution_stack,
        execution_id=execution_id,
        step_id="step_b",
        payload={"output": {"value": "b"}},
    )
    await workflow_execution_stack.scheduler_service.tick()

    checkpoints_before = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/checkpoints?include_superseded=true"
    )
    checkpoint_numbers = [
        item["checkpoint_number"] for item in checkpoints_before.json()["items"]
    ]
    assert checkpoints_before.status_code == 200
    assert checkpoint_numbers == [1, 2, 3]

    execution = await workflow_execution_stack.execution_repository.get_execution_by_id(
        execution_id
    )
    assert execution is not None
    await workflow_execution_stack.execution_repository.update_execution_status(
        execution,
        ExecutionStatus.failed,
        completed_at=datetime.now(UTC),
    )

    rolled_back = await workflow_execution_client.post(
        f"/api/v1/executions/{execution_id}/rollback/2",
        json={"reason": "step_c failed"},
    )
    checkpoints = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/checkpoints?include_superseded=true"
    )
    journal = await workflow_execution_stack.execution_service.get_journal(execution_id)

    assert rolled_back.status_code == 200
    assert rolled_back.json()["target_checkpoint_number"] == 2
    assert checkpoints.status_code == 200
    assert checkpoints.json()["items"][-1]["superseded"] is True
    assert any(item.event_type == ExecutionEventType.rolled_back for item in journal.items)

    resumed = await workflow_execution_stack.execution_service.resume_execution(execution_id)
    workflow_execution_stack.runtime_controller_stub.dispatch.reset_mock()
    await workflow_execution_stack.scheduler_service.tick()
    dispatched = [
        call.args[0]["step_id"]
        for call in workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list
    ]
    assert resumed.parent_execution_id == execution_id
    assert dispatched == ["step_b"]


@pytest.mark.asyncio
async def test_checkpoint_rollback_rejects_active_execution_and_missing_permission(
    workflow_execution_stack,
    workflow_execution_client,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Rollback guards",
        yaml_source="""
schema_version: 1
steps:
  - id: guard_step
    step_type: tool_call
    tool_fqn: ops.guard
""",
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
    )
    await workflow_execution_stack.scheduler_service.tick()

    checkpoints_before = await workflow_execution_client.get(
        f"/api/v1/executions/{execution_id}/checkpoints"
    )
    checkpoint_numbers = [
        item["checkpoint_number"] for item in checkpoints_before.json()["items"]
    ]
    assert checkpoints_before.status_code == 200
    assert checkpoint_numbers == [1]

    workflow_execution_stack.current_user["permissions"] = []
    forbidden = await workflow_execution_client.post(
        f"/api/v1/executions/{execution_id}/rollback/1",
        json={},
    )
    assert forbidden.status_code == 403

    workflow_execution_stack.current_user["permissions"] = ["execution.rollback"]
    conflict = await workflow_execution_client.post(
        f"/api/v1/executions/{execution_id}/rollback/1",
        json={},
    )
    assert conflict.status_code == 409
