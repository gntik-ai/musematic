from __future__ import annotations

from uuid import uuid4

import pytest

from platform.execution.models import ExecutionCheckpoint, ExecutionEventType

from tests.integration.execution.support import (
    create_execution,
    create_workflow,
    mark_step_completed,
    mark_step_failed,
)


WORKFLOW_YAML = """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops.fetch
  - id: step_b
    step_type: tool_call
    tool_fqn: ops.enrich
    depends_on: [step_a]
  - id: step_c
    step_type: tool_call
    tool_fqn: ops.finalize
    depends_on: [step_b]
"""


@pytest.mark.asyncio
async def test_replay_resume_and_rerun_preserve_execution_lineage(
    workflow_execution_stack,
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Replay Workflow",
        yaml_source=WORKFLOW_YAML,
    )

    completed_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        input_parameters={"run": "completed"},
    )
    await mark_step_completed(
        workflow_execution_stack,
        execution_id=completed_execution_id,
        step_id="step_a",
        payload={"output": {"value": "A"}},
    )
    await mark_step_completed(
        workflow_execution_stack,
        execution_id=completed_execution_id,
        step_id="step_b",
        payload={"output": {"value": "B"}},
    )
    await mark_step_completed(
        workflow_execution_stack,
        execution_id=completed_execution_id,
        step_id="step_c",
        payload={"output": {"value": "C"}},
        execution_completed=True,
    )

    original_state = await workflow_execution_stack.execution_service.get_execution_state(
        completed_execution_id
    )
    event_count_before = await workflow_execution_stack.execution_repository.count_events(
        completed_execution_id
    )
    replayed_state = await workflow_execution_stack.execution_service.replay_execution(
        completed_execution_id
    )

    assert replayed_state.status == original_state.status
    assert replayed_state.completed_step_ids == original_state.completed_step_ids
    assert replayed_state.step_results == original_state.step_results
    assert (
        await workflow_execution_stack.execution_repository.count_events(completed_execution_id)
    ) == event_count_before

    failed_execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        input_parameters={"run": "resume"},
    )
    await mark_step_completed(
        workflow_execution_stack,
        execution_id=failed_execution_id,
        step_id="step_a",
        payload={"output": {"value": "A"}},
    )
    await mark_step_completed(
        workflow_execution_stack,
        execution_id=failed_execution_id,
        step_id="step_b",
        payload={"output": {"value": "B"}},
    )
    state_before_failure = await workflow_execution_stack.execution_service.get_execution_state(
        failed_execution_id
    )
    await workflow_execution_stack.execution_repository.create_checkpoint(
        ExecutionCheckpoint(
            execution_id=failed_execution_id,
            last_event_sequence=state_before_failure.last_event_sequence,
            completed_step_ids=list(state_before_failure.completed_step_ids),
            pending_step_ids=list(state_before_failure.pending_step_ids),
            active_step_ids=list(state_before_failure.active_step_ids),
            step_results=dict(state_before_failure.step_results),
            execution_data={},
        )
    )
    await mark_step_failed(
        workflow_execution_stack,
        execution_id=failed_execution_id,
        step_id="step_c",
        payload={"error": "boom"},
    )

    workflow_execution_stack.runtime_controller_stub.dispatch.reset_mock()
    resumed = await workflow_execution_stack.execution_service.resume_execution(failed_execution_id)
    await workflow_execution_stack.scheduler_service.tick()
    resumed_calls = [
        call.args[0]["step_id"]
        for call in workflow_execution_stack.runtime_controller_stub.dispatch.await_args_list
        if call.args and call.args[0]["execution_id"] == str(resumed.id)
    ]

    assert resumed.parent_execution_id == failed_execution_id
    assert resumed_calls == ["step_c"]

    rerun = await workflow_execution_stack.execution_service.rerun_execution(
        completed_execution_id,
        {"run": "rerun"},
    )
    rerun_journal = await workflow_execution_stack.execution_service.get_journal(rerun.id)

    assert rerun.rerun_of_execution_id == completed_execution_id
    assert rerun.workflow_version_id == original_state.workflow_version_id
    assert rerun_journal.items[0].event_type == ExecutionEventType.created
    assert rerun_journal.items[0].sequence == 1
