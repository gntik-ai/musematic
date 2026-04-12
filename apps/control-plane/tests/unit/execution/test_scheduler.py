from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.execution.models import ExecutionStatus
from platform.execution.projector import ExecutionProjector
from platform.execution.scheduler import PriorityScorer, SchedulerService
from platform.execution.schemas import ExecutionCreate
from platform.execution.service import ExecutionService
from platform.workflows.schemas import WorkflowCreate
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


def _build_scheduler() -> tuple[
    WorkflowService, ExecutionService, SchedulerService, FakeRuntimeController
]:
    workflow_repository = FakeWorkflowRepository()
    execution_repository = FakeExecutionRepository()
    producer = FakeProducer()
    redis_client = FakeRedisClient()
    object_storage = FakeObjectStorage()
    runtime_controller = FakeRuntimeController()
    workflow_service = WorkflowService(
        repository=cast(Any, workflow_repository),
        settings=make_settings(),
        producer=cast(Any, producer),
    )
    execution_service = ExecutionService(
        repository=cast(Any, execution_repository),
        settings=make_settings(),
        producer=cast(Any, producer),
        redis_client=cast(Any, redis_client),
        object_storage=cast(Any, object_storage),
        runtime_controller=runtime_controller,
        reasoning_engine=None,
        context_engineering_service=None,
        projector=ExecutionProjector(),
    )
    execution_service.workflow_repository = cast(Any, workflow_repository)
    scheduler = SchedulerService(
        repository=cast(Any, execution_repository),
        execution_service=execution_service,
        projector=ExecutionProjector(),
        settings=make_settings(),
        producer=cast(Any, producer),
        redis_client=redis_client,
        object_storage=object_storage,
        runtime_controller=runtime_controller,
        reasoning_engine=None,
        context_engineering_service=None,
        interactions_service=None,
        priority_scorer=PriorityScorer(),
    )
    return workflow_service, execution_service, scheduler, runtime_controller


@pytest.mark.asyncio
async def test_scheduler_dispatches_runnable_step_and_persists_task_plan() -> None:
    workflow_service, execution_service, scheduler, runtime_controller = _build_scheduler()
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Scheduler Workflow",
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
    depends_on: [step_a]
            """.strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    execution = await execution_service.create_execution(
        ExecutionCreate(workflow_definition_id=workflow.id, workspace_id=workspace_id),
        created_by=actor_id,
    )

    await scheduler.tick()

    assert runtime_controller.dispatch_calls[0]["step_id"] == "step_a"
    task_plan = await execution_service.get_task_plan(execution.id, None)
    assert isinstance(task_plan, list)
    assert task_plan[0].step_id == "step_a"


@pytest.mark.asyncio
async def test_scheduler_handles_approval_waits_and_timeouts() -> None:
    workflow_service, execution_service, scheduler, runtime_controller = _build_scheduler()
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Approval Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: step_a
    step_type: approval_gate
    approval_config:
      required_approvers: [ops]
      timeout_seconds: 1
      timeout_action: fail
            """.strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    execution = await execution_service.create_execution(
        ExecutionCreate(workflow_definition_id=workflow.id, workspace_id=workspace_id),
        created_by=actor_id,
    )
    await scheduler.tick()

    waits = await execution_service.list_approvals(execution.id)
    assert waits.total == 1
    assert runtime_controller.dispatch_calls == []

    approval_wait = await execution_service.repository.get_approval_wait(execution.id, "step_a")
    assert approval_wait is not None
    approval_wait.timeout_at = datetime.now(UTC) - timedelta(seconds=5)
    await scheduler.scan_approval_timeouts()
    updated_execution = await execution_service.get_execution(execution.id)

    assert updated_execution.status == ExecutionStatus.failed


@pytest.mark.asyncio
async def test_scheduler_reprioritizes() -> None:
    workflow_service, execution_service, scheduler, _ = _build_scheduler()
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Priority Workflow",
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
    execution = await execution_service.create_execution(
        ExecutionCreate(
            workflow_definition_id=workflow.id,
            workspace_id=workspace_id,
            sla_deadline=datetime.now(UTC) + timedelta(minutes=2),
        ),
        created_by=actor_id,
    )

    await scheduler.handle_reprioritization_trigger("external_event", execution.id)
    journal = await execution_service.get_journal(execution.id)

    assert any(item.event_type.value == "reprioritized" for item in journal.items)
