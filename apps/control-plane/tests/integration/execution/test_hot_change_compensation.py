from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from platform.common.exceptions import ValidationError
from platform.execution.exceptions import HotChangeIncompatibleError
from platform.execution.models import (
    ExecutionCompensationRecord,
    ExecutionEventType,
    ExecutionStatus,
)
from platform.workflows.schemas import WorkflowUpdate

from tests.integration.execution.support import (
    create_execution,
    create_workflow,
    mark_step_completed,
)


INITIAL_YAML = """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
    compensation_handler: undo_step_a
  - id: step_b
    step_type: tool_call
    tool_fqn: ops.transform
    depends_on: [step_a]
  - id: step_c
    step_type: tool_call
    tool_fqn: ops.publish
    depends_on: [step_b]
"""

COMPATIBLE_YAML = """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
    compensation_handler: undo_step_a
  - id: step_b
    step_type: tool_call
    tool_fqn: ops.transform
    depends_on: [step_a]
  - id: step_c
    step_type: tool_call
    tool_fqn: ops.publish
    depends_on: [step_b]
  - id: step_d
    step_type: tool_call
    tool_fqn: ops.archive
    depends_on: [step_c]
"""

INCOMPATIBLE_YAML = """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
    compensation_handler: undo_step_a
  - id: step_c
    step_type: tool_call
    tool_fqn: ops.publish
    depends_on: [step_a]
"""


@pytest.mark.asyncio
async def test_hot_change_and_compensation_paths_are_persisted_correctly(
    workflow_execution_stack,
    integration_session,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Hot Change Workflow",
        yaml_source=INITIAL_YAML,
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
    )

    await mark_step_completed(
        workflow_execution_stack,
        execution_id=execution_id,
        step_id="step_a",
        payload={"output": {"value": "A"}},
    )
    await workflow_execution_stack.execution_service.record_runtime_event(
        execution_id,
        step_id="step_b",
        event_type=ExecutionEventType.dispatched,
        payload={"step_type": "tool_call"},
        status=ExecutionStatus.running,
    )

    compatible_version = await workflow_execution_stack.workflow_service.update_workflow(
        workflow_id,
        WorkflowUpdate(yaml_source=COMPATIBLE_YAML.strip(), change_summary="add step_d"),
        UUID(workflow_execution_stack.current_user["sub"]),
    )
    assert compatible_version.current_version is not None

    applied = await workflow_execution_stack.execution_service.apply_hot_change(
        execution_id,
        compatible_version.current_version.id,
    )
    journal_after_apply = await workflow_execution_stack.execution_service.get_journal(execution_id)

    assert applied.workflow_version_id == compatible_version.current_version.id
    assert any(
        event.event_type == ExecutionEventType.hot_changed for event in journal_after_apply.items
    )

    incompatible_version = await workflow_execution_stack.workflow_service.update_workflow(
        workflow_id,
        WorkflowUpdate(yaml_source=INCOMPATIBLE_YAML.strip(), change_summary="remove step_b"),
        UUID(workflow_execution_stack.current_user["sub"]),
    )
    assert incompatible_version.current_version is not None

    with pytest.raises(HotChangeIncompatibleError):
        await workflow_execution_stack.execution_service.apply_hot_change(
            execution_id,
            incompatible_version.current_version.id,
        )

    execution = await workflow_execution_stack.execution_repository.get_execution_by_id(execution_id)
    assert execution is not None
    assert execution.workflow_version_id == compatible_version.current_version.id

    await workflow_execution_stack.execution_service.trigger_compensation(
        execution_id,
        "step_a",
        triggered_by="user",
    )
    compensation_records = list(
        (
            await integration_session.execute(
                select(ExecutionCompensationRecord).where(
                    ExecutionCompensationRecord.execution_id == execution_id
                )
            )
        )
        .scalars()
        .all()
    )
    step_a_record = next(record for record in compensation_records if record.step_id == "step_a")
    assert step_a_record.outcome.value == "completed"

    await mark_step_completed(
        workflow_execution_stack,
        execution_id=execution_id,
        step_id="step_b",
        payload={"output": {"value": "B"}},
    )
    await workflow_execution_stack.execution_service.trigger_compensation(
        execution_id,
        "step_b",
        triggered_by="user",
    )
    compensation_records = list(
        (
            await integration_session.execute(
                select(ExecutionCompensationRecord).where(
                    ExecutionCompensationRecord.execution_id == execution_id
                )
            )
        )
        .scalars()
        .all()
    )
    step_b_record = next(record for record in compensation_records if record.step_id == "step_b")
    assert step_b_record.outcome.value == "not_available"

    await workflow_execution_stack.execution_service.record_runtime_event(
        execution_id,
        step_id="step_c",
        event_type=ExecutionEventType.dispatched,
        payload={"step_type": "tool_call"},
        status=ExecutionStatus.running,
    )
    with pytest.raises(ValidationError, match="Only completed steps can be compensated"):
        await workflow_execution_stack.execution_service.trigger_compensation(
            execution_id,
            "step_c",
            triggered_by="user",
        )

    journal = await workflow_execution_stack.execution_service.get_journal(execution_id)
    assert any(item.event_type == ExecutionEventType.compensated for item in journal.items)
    assert any(
        item.event_type == ExecutionEventType.compensation_failed for item in journal.items
    )
