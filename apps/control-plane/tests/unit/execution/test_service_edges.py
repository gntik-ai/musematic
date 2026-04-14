from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import ObjectNotFoundError, ValidationError
from platform.execution.exceptions import (
    ApprovalAlreadyDecidedError,
    ExecutionAlreadyRunningError,
    ExecutionNotFoundError,
)
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
from platform.workflows.exceptions import WorkflowNotFoundError
from platform.workflows.models import TriggerType
from platform.workflows.schemas import TriggerCreate, WorkflowCreate
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


class _MissingObjectStorage(FakeObjectStorage):
    async def download_object(self, bucket: str, key: str) -> bytes:
        del bucket, key
        raise ObjectNotFoundError("missing")


def _build_services(
    *,
    object_storage: FakeObjectStorage | None = None,
) -> tuple[WorkflowService, ExecutionService, FakeWorkflowRepository, FakeExecutionRepository]:
    workflow_repository = FakeWorkflowRepository()
    execution_repository = FakeExecutionRepository()
    producer = FakeProducer()
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
        object_storage=cast(Any, object_storage or FakeObjectStorage()),
        runtime_controller=FakeRuntimeController(),
        reasoning_engine=None,
        context_engineering_service=None,
        projector=ExecutionProjector(),
    )
    execution_service.workflow_repository = cast(Any, workflow_repository)
    return workflow_service, execution_service, workflow_repository, execution_repository


@pytest.mark.asyncio
async def test_execution_service_rejects_missing_resources_and_trigger_limits() -> None:
    workflow_service, execution_service, workflow_repository, _ = _build_services()
    actor_id = uuid4()
    workspace_id = uuid4()

    with pytest.raises(WorkflowNotFoundError):
        await execution_service.create_execution(
            ExecutionCreate(workflow_definition_id=uuid4(), workspace_id=workspace_id),
            created_by=actor_id,
        )

    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Edge Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: agents.alpha
            """.strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )

    with pytest.raises(ValidationError, match="Trigger does not exist"):
        await execution_service.create_execution(
            ExecutionCreate(
                workflow_definition_id=workflow.id,
                trigger_id=uuid4(),
                workspace_id=workspace_id,
            ),
            created_by=actor_id,
        )

    with pytest.raises(WorkflowNotFoundError):
        await execution_service.create_execution(
            ExecutionCreate(
                workflow_definition_id=workflow.id,
                workflow_version_id=uuid4(),
                workspace_id=workspace_id,
            ),
            created_by=actor_id,
        )

    trigger = await workflow_service.create_trigger(
        workflow.id,
        TriggerCreate(
            trigger_type=TriggerType.webhook,
            name="limited",
            max_concurrent_executions=1,
            config={"secret": "token"},
        ),
    )
    await execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow.id,
            trigger_id=trigger.id,
            trigger_type=TriggerType.webhook,
            workspace_id=workspace_id,
        ),
        created_by=actor_id,
    )

    with pytest.raises(ValidationError, match="concurrency limit reached"):
        await execution_service.create_execution(
            ExecutionCreate(
                workflow_definition_id=workflow.id,
                trigger_id=trigger.id,
                trigger_type=TriggerType.webhook,
                workspace_id=workspace_id,
            ),
            created_by=actor_id,
        )

    workflow_repository.definitions[workflow.id].current_version = None
    with pytest.raises(WorkflowNotFoundError):
        await execution_service.create_execution(
            ExecutionCreate(workflow_definition_id=workflow.id, workspace_id=workspace_id),
            created_by=actor_id,
        )


@pytest.mark.asyncio
async def test_execution_service_covers_runtime_error_paths_and_missing_task_plan_payloads(
) -> None:
    workflow_service, execution_service, _, execution_repository = _build_services(
        object_storage=_MissingObjectStorage()
    )
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Runtime Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: agents.alpha
  - id: step_b
    step_type: approval_gate
    depends_on: [step_a]
    approval_config:
      required_approvers: [ops]
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
        ),
        created_by=actor_id,
        precompleted_step_ids=["missing-step"],
    )
    stored_execution = execution_repository.executions[execution.id]
    stored_execution.status = ExecutionStatus.running

    with pytest.raises(ExecutionAlreadyRunningError):
        await execution_service.resume_execution(execution.id)

    stored_execution.status = ExecutionStatus.completed
    with pytest.raises(ValidationError, match="cannot be canceled"):
        await execution_service.cancel_execution(execution.id)

    with pytest.raises(ValidationError, match="Approval wait does not exist"):
        await execution_service.record_approval_decision(
            execution.id,
            "step_b",
            ApprovalDecisionRequest(decision=ApprovalDecision.approved),
            decided_by=actor_id,
        )

    wait = await execution_service.repository.create_approval_wait(
        ExecutionApprovalWait(
            execution_id=execution.id,
            step_id="step_b",
            required_approvers=["ops"],
            timeout_at=datetime.now(UTC),
            timeout_action=ApprovalTimeoutAction.fail,
            decision=ApprovalDecision.rejected,
            decided_by="ops",
            decided_at=datetime.now(UTC),
            interaction_message_id=None,
        )
    )
    assert wait.decision is ApprovalDecision.rejected
    with pytest.raises(ApprovalAlreadyDecidedError):
        await execution_service.record_approval_decision(
            execution.id,
            "step_b",
            ApprovalDecisionRequest(decision=ApprovalDecision.approved),
            decided_by=actor_id,
        )

    with pytest.raises(WorkflowNotFoundError):
        await execution_service.validate_hot_change(execution.id, uuid4())

    with pytest.raises(ValidationError, match="does not exist"):
        await execution_service.get_task_plan(execution.id, "missing-step")

    await execution_service.repository.upsert_task_plan_record(
        ExecutionTaskPlanRecord(
            execution_id=execution.id,
            step_id="step_a",
            selected_agent_fqn="agents.alpha",
            selected_tool_fqn=None,
            rationale_summary="agent",
            considered_agents_count=1,
            considered_tools_count=0,
            rejected_alternatives_count=0,
            parameter_sources=["input"],
            storage_key="plans/missing.json",
            storage_size_bytes=0,
        )
    )
    missing_payload = await execution_service.get_task_plan(execution.id, "step_a")
    assert missing_payload.parameters == {}

    with pytest.raises(ValidationError, match="does not exist"):
        await execution_service.trigger_compensation(
            execution.id,
            "missing-step",
            triggered_by="ops",
        )

    with pytest.raises(ExecutionNotFoundError):
        await execution_service.get_execution(uuid4())
