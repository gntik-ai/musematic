from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.execution.models import (
    ApprovalTimeoutAction,
    ExecutionApprovalWait,
    ExecutionEventType,
    ExecutionStatus,
    ExecutionTaskPlanRecord,
)
from platform.execution.router import (
    cancel_execution,
    create_execution,
    decide_approval,
    get_execution,
    get_execution_journal,
    get_execution_state,
    get_task_plan,
    hot_change_execution,
    list_approvals,
    list_executions,
    list_task_plans,
    replay_execution,
    rerun_execution,
    resume_execution,
    trigger_compensation,
)
from platform.execution.schemas import ApprovalDecisionRequest, ExecutionCreate, HotChangeRequest
from platform.workflows.schemas import WorkflowCreate, WorkflowUpdate
from typing import Any
from uuid import uuid4

import pytest

from tests.unit.execution.test_service import _build_services


@pytest.mark.asyncio
async def test_execution_router_functions_cover_lifecycle_paths() -> None:
    workflow_service, execution_service, object_storage = _build_services()
    current_user: dict[str, Any] = {"sub": str(uuid4())}
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Execution Router Workflow",
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

    created = await create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow.id,
            workspace_id=workspace_id,
            input_parameters={"invoice_id": "INV-1"},
        ),
        current_user,
        execution_service,
    )
    listed = await list_executions(
        workspace_id,
        None,
        None,
        None,
        None,
        None,
        1,
        20,
        current_user,
        execution_service,
    )
    fetched = await get_execution(created.id, current_user, execution_service)
    state = await get_execution_state(created.id, current_user, execution_service)
    journal = await get_execution_journal(
        created.id,
        None,
        None,
        current_user,
        execution_service,
    )

    assert listed.total == 1
    assert fetched.id == created.id
    assert state.pending_step_ids == ["step_a", "step_b", "step_c"]
    assert journal.total == 1

    await execution_service.record_runtime_event(
        created.id,
        step_id="step_a",
        event_type=ExecutionEventType.completed,
        payload={"output": {"ok": True}},
        status=ExecutionStatus.running,
    )
    await execution_service.repository.create_approval_wait(
        ExecutionApprovalWait(
            execution_id=created.id,
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

    approvals = await list_approvals(created.id, current_user, execution_service)
    decision = await decide_approval(
        created.id,
        "step_b",
        ApprovalDecisionRequest(decision="approved", comment="ok"),
        current_user,
        execution_service,
    )

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
    hot_changed = await hot_change_execution(
        created.id,
        HotChangeRequest(new_version_id=workflow_update.current_version.id),
        current_user,
        execution_service,
    )

    await object_storage.create_bucket_if_not_exists(execution_service.task_plan_bucket)
    await object_storage.upload_object(
        execution_service.task_plan_bucket,
        f"{created.id}/step_c/task-plan.json",
        json.dumps(
            {
                "considered_agents": [{"fqn": "ns:a"}],
                "considered_tools": [{"fqn": "ns:tool"}],
                "parameters": {
                    "invoice_id": {
                        "value": "INV-1",
                        "provenance": "user_input",
                    }
                },
                "rejected_alternatives": [],
            }
        ).encode("utf-8"),
    )
    await execution_service.repository.upsert_task_plan_record(
        ExecutionTaskPlanRecord(
            execution_id=created.id,
            step_id="step_c",
            selected_agent_fqn=None,
            selected_tool_fqn="ns:tool",
            rationale_summary="tool",
            considered_agents_count=1,
            considered_tools_count=1,
            rejected_alternatives_count=0,
            parameter_sources=["user_input"],
            storage_key=f"{created.id}/step_c/task-plan.json",
            storage_size_bytes=32,
        )
    )
    task_plan_list = await list_task_plans(created.id, current_user, execution_service)
    task_plan = await get_task_plan(created.id, "step_c", current_user, execution_service)

    await execution_service.record_runtime_event(
        created.id,
        step_id="step_c",
        event_type=ExecutionEventType.completed,
        payload={"output": {"ok": True}},
        status=ExecutionStatus.failed,
    )
    replayed = await replay_execution(created.id, current_user, execution_service)
    resumed = await resume_execution(created.id, current_user, execution_service)
    rerun = await rerun_execution(
        created.id,
        {"input_overrides": {"invoice_id": "INV-2"}},
        current_user,
        execution_service,
    )
    canceled = await cancel_execution(rerun.id, current_user, execution_service)
    compensation_response = await trigger_compensation(
        created.id,
        "step_c",
        current_user,
        execution_service,
    )

    assert approvals.total == 1
    assert decision.decision is not None
    assert decision.decision.value == "approved"
    assert hot_changed.result.compatible is True
    assert len(task_plan_list) == 1
    assert task_plan.parameters["invoice_id"]["provenance"] == "user_input"
    assert replayed.last_event_sequence >= 4
    assert resumed.parent_execution_id == created.id
    assert canceled.status == ExecutionStatus.canceled
    assert compensation_response.status_code == 202
