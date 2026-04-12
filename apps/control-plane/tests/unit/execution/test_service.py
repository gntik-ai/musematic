from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.execution.models import (
    ApprovalDecision,
    ApprovalTimeoutAction,
    ExecutionApprovalWait,
    ExecutionStatus,
    ExecutionTaskPlanRecord,
)
from platform.execution.projector import ExecutionProjector
from platform.execution.schemas import ApprovalDecisionRequest, ExecutionCreate
from platform.execution.service import ExecutionService
from platform.workflows.schemas import WorkflowCreate, WorkflowUpdate
from platform.workflows.service import WorkflowService
from typing import Any, cast
from uuid import uuid4

import pytest

from tests.workflow_execution_support import (
    FakeExecutionRepository,
    FakeObjectStorage,
    FakeProducer,
    FakeRedisClient,
    FakeRuntimeController,
    FakeWorkflowRepository,
    make_settings,
)


def _build_services() -> tuple[WorkflowService, ExecutionService, FakeObjectStorage]:
    workflow_repository = FakeWorkflowRepository()
    execution_repository = FakeExecutionRepository()
    producer = FakeProducer()
    object_storage = FakeObjectStorage()
    workflow_service = WorkflowService(
        repository=cast(Any, workflow_repository),
        settings=make_settings(),
        producer=cast(Any, producer),
    )
    execution_service = ExecutionService(
        repository=cast(Any, execution_repository),
        settings=make_settings(),
        producer=cast(Any, producer),
        redis_client=cast(Any, FakeRedisClient()),
        object_storage=cast(Any, object_storage),
        runtime_controller=FakeRuntimeController(),
        reasoning_engine=None,
        context_engineering_service=None,
        projector=ExecutionProjector(),
    )
    execution_service.workflow_repository = cast(Any, workflow_repository)
    return workflow_service, execution_service, object_storage


@pytest.mark.asyncio
async def test_execution_service_supports_core_lifecycle_flows() -> None:
    workflow_service, execution_service, object_storage = _build_services()
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Execution Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
  - id: step_b
    step_type: approval_gate
    depends_on: [step_a]
    approval_config:
      required_approvers: [ops]
  - id: step_c
    step_type: tool_call
    tool_fqn: ns:tool
    depends_on: [step_b]
    compensation_handler: undo_step_c
            """.strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    execution = await execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow.id,
            workspace_id=workspace_id,
            input_parameters={"invoice_id": "INV-1"},
        ),
        created_by=actor_id,
    )
    initial_state = await execution_service.get_execution_state(execution.id)
    journal = await execution_service.get_journal(execution.id)
    assert initial_state.pending_step_ids == ["step_a", "step_b", "step_c"]
    assert journal.total == 1

    await execution_service.record_runtime_event(
        execution.id,
        step_id="step_a",
        event_type=__import__(
            "platform.execution.models",
            fromlist=["ExecutionEventType"],
        ).ExecutionEventType.completed,
        payload={"output": {"ok": True}},
        status=ExecutionStatus.running,
    )
    state_after_step = await execution_service.get_execution_state(execution.id)
    assert "step_a" in state_after_step.completed_step_ids

    approval = await execution_service.repository.create_approval_wait(
        ExecutionApprovalWait(
            execution_id=execution.id,
            step_id="step_b",
            required_approvers=["ops"],
            timeout_at=datetime.now(UTC),
            timeout_action=ApprovalTimeoutAction.fail,
            decision=None,
            decided_by=None,
            decided_at=None,
            interaction_message_id=None,
        )
    )
    del approval
    approval_response = await execution_service.record_approval_decision(
        execution.id,
        "step_b",
        ApprovalDecisionRequest(decision=ApprovalDecision.approved, comment="ok"),
        decided_by=actor_id,
    )
    assert approval_response.decision == ApprovalDecision.approved

    workflow_update = await workflow_service.update_workflow(
        workflow.id,
        WorkflowUpdate(
            yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
  - id: step_b
    step_type: approval_gate
    depends_on: [step_a]
    approval_config:
      required_approvers: [ops]
  - id: step_c
    step_type: tool_call
    tool_fqn: ns:tool
    depends_on: [step_b]
    compensation_handler: undo_step_c
  - id: step_d
    step_type: tool_call
    tool_fqn: ns:another
    depends_on: [step_c]
            """.strip(),
        ),
        actor_id,
    )
    assert workflow_update.current_version is not None
    compatibility = await execution_service.validate_hot_change(
        execution.id,
        workflow_update.current_version.id,
    )
    assert compatibility.compatible is True
    hot_changed = await execution_service.apply_hot_change(
        execution.id,
        workflow_update.current_version.id,
    )
    assert hot_changed.workflow_version_id == workflow_update.current_version.id

    stored_execution = await execution_service.repository.get_execution_by_id(execution.id)
    assert stored_execution is not None
    await execution_service.repository.update_execution_status(
        stored_execution,
        ExecutionStatus.failed,
        completed_at=datetime.now(UTC),
    )
    resumed = await execution_service.resume_execution(execution.id)
    rerun = await execution_service.rerun_execution(execution.id, {"invoice_id": "INV-2"})
    assert resumed.parent_execution_id == execution.id
    assert rerun.rerun_of_execution_id == execution.id

    await object_storage.create_bucket_if_not_exists(execution_service.task_plan_bucket)
    await object_storage.upload_object(
        execution_service.task_plan_bucket,
        f"{execution.id}/step_c/task-plan.json",
        json.dumps(
            {
                "considered_agents": [{"fqn": "ns:a"}],
                "considered_tools": [{"fqn": "ns:tool"}],
                "parameters": {"invoice_id": {"value": "INV-1", "provenance": "user_input"}},
                "rejected_alternatives": [],
            }
        ).encode("utf-8"),
    )
    await execution_service.repository.upsert_task_plan_record(
        ExecutionTaskPlanRecord(
            execution_id=execution.id,
            step_id="step_c",
            selected_agent_fqn=None,
            selected_tool_fqn="ns:tool",
            rationale_summary="tool",
            considered_agents_count=1,
            considered_tools_count=1,
            rejected_alternatives_count=0,
            parameter_sources=["user_input"],
            storage_key=f"{execution.id}/step_c/task-plan.json",
            storage_size_bytes=32,
        )
    )
    task_plan = await execution_service.get_task_plan(execution.id, "step_c")
    assert not isinstance(task_plan, list)
    assert task_plan.parameters["invoice_id"]["provenance"] == "user_input"

    await execution_service.record_runtime_event(
        execution.id,
        step_id="step_c",
        event_type=__import__(
            "platform.execution.models",
            fromlist=["ExecutionEventType"],
        ).ExecutionEventType.completed,
        payload={"output": {"ok": True}},
        status=ExecutionStatus.running,
    )
    await execution_service.trigger_compensation(
        execution.id,
        "step_c",
        triggered_by="user",
    )
    canceled = await execution_service.cancel_execution(rerun.id)
    replayed = await execution_service.replay_execution(execution.id)

    assert canceled.status == ExecutionStatus.canceled
    assert replayed.last_event_sequence >= 4
