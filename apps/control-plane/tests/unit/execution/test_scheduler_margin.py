from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.execution.models import (
    ApprovalTimeoutAction,
    ExecutionDispatchLease,
    ExecutionStatus,
    ReprioritizationTrigger,
)
from platform.execution.projector import ExecutionProjector
from platform.execution.reprioritization import ReprioritizationFiring, ReprioritizationResult
from platform.execution.scheduler import PriorityScorer, SchedulerService
from platform.execution.schemas import ExecutionCreate, ExecutionStateResponse
from platform.execution.service import ExecutionService
from platform.workflows.ir import ApprovalConfigIR, StepIR, WorkflowIR
from platform.workflows.schemas import WorkflowCreate
from platform.workflows.service import WorkflowService
from textwrap import dedent
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
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


class _RedisWithExists(FakeRedisClient):
    async def exists(self, key: str) -> int:
        return 1 if key in self.storage else 0


class _FailingObjectStorage(FakeObjectStorage):
    async def upload_object(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> None:
        del bucket, key, data, content_type, metadata
        raise RuntimeError("storage unavailable")


class _FailingLaunchRuntime:
    def __init__(self) -> None:
        self.dispatched: list[dict[str, Any]] = []

    async def launch_runtime(self, payload: dict[str, Any], *, prefer_warm: bool) -> None:
        del payload, prefer_warm
        raise RuntimeError("warm pool unavailable")

    async def dispatch(self, payload: dict[str, Any]) -> None:
        self.dispatched.append(payload)


def _build_scheduler(
    *,
    redis_client: FakeRedisClient | None = None,
    object_storage: FakeObjectStorage | None = None,
) -> tuple[WorkflowService, ExecutionService, SchedulerService]:
    workflow_repository = FakeWorkflowRepository()
    execution_repository = FakeExecutionRepository()
    producer = FakeProducer()
    redis = redis_client or FakeRedisClient()
    storage = object_storage or FakeObjectStorage()
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
        redis_client=cast(Any, redis),
        object_storage=cast(Any, storage),
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
        redis_client=redis,
        object_storage=storage,
        runtime_controller=runtime_controller,
        reasoning_engine=None,
        context_engineering_service=None,
        interactions_service=None,
        priority_scorer=PriorityScorer(),
    )
    return workflow_service, execution_service, scheduler


@pytest.mark.asyncio
async def test_scheduler_tick_reprioritizes_queue_per_workspace() -> None:
    workflow_service, execution_service, scheduler = _build_scheduler()
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Queue Workflow",
            description=None,
            yaml_source=dedent("""
                schema_version: 1
                steps:
                  - id: step_a
                    step_type: agent_task
                    agent_fqn: ns:a
            """).strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    first = await execution_service.create_execution(
        ExecutionCreate(workflow_definition_id=workflow.id, workspace_id=workspace_id),
        created_by=actor_id,
    )
    second = await execution_service.create_execution(
        ExecutionCreate(workflow_definition_id=workflow.id, workspace_id=workspace_id),
        created_by=actor_id,
    )

    trigger = ReprioritizationTrigger(
        workspace_id=workspace_id,
        name="urgent",
        trigger_type="sla_approach",
        condition_config={"threshold_fraction": 0.2},
        action="promote_to_front",
        priority_rank=1,
        enabled=True,
        created_by=None,
    )
    trigger.id = uuid4()
    trigger.created_at = datetime.now(UTC)
    trigger.updated_at = trigger.created_at

    scheduler.reprioritization_service = SimpleNamespace(
        evaluate_for_dispatch_cycle=AsyncMock(
            return_value=ReprioritizationResult(
                ordered_executions=[second, first],
                firings=[
                    ReprioritizationFiring(
                        execution_id=second.id,
                        trigger=trigger,
                        old_position=2,
                        new_position=1,
                        remaining_fraction=0.1,
                    )
                ],
            )
        )
    )
    scheduler._process_execution = AsyncMock()  # type: ignore[method-assign]
    execution_service.publish_reprioritization = AsyncMock()  # type: ignore[method-assign]

    await scheduler.tick()

    assert scheduler.reprioritization_service.evaluate_for_dispatch_cycle.await_count == 1
    processed = [
        call.args[0].id
        for call in scheduler._process_execution.await_args_list  # type: ignore[attr-defined]
    ]
    assert processed == [second.id, first.id]


@pytest.mark.asyncio
async def test_scheduler_helper_paths_cover_checkpoint_persistence_and_retry_recovery() -> None:
    workflow_service, execution_service, scheduler = _build_scheduler(
        redis_client=_RedisWithExists(),
        object_storage=_FailingObjectStorage(),
    )
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Helper Workflow",
            description=None,
            yaml_source=dedent("""
                schema_version: 1
                steps:
                  - id: step_a
                    step_type: tool_call
                    tool_fqn: ns:tool
            """).strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    execution = await execution_service.create_execution(
        ExecutionCreate(workflow_definition_id=workflow.id, workspace_id=workspace_id),
        created_by=actor_id,
    )
    state = ExecutionStateResponse(
        execution_id=execution.id,
        status=ExecutionStatus.running,
        completed_step_ids=[],
        active_step_ids=["step_a"],
        pending_step_ids=["step_a"],
        step_results={"_execution_data": {"cursor": "a"}},
        last_event_sequence=1,
        workflow_version_id=execution.workflow_version_id,
    )
    step = StepIR(step_id="step_a", step_type="tool_call", tool_fqn="ns:tool")

    scheduler.checkpoint_service = SimpleNamespace(
        should_capture=lambda item, policy: True,
        capture=AsyncMock(side_effect=RuntimeError("snapshot failed")),
    )
    captured = await scheduler._capture_pre_dispatch_checkpoint(execution, step, state)
    assert captured is False
    assert execution.status is ExecutionStatus.paused

    await scheduler._persist_task_plan(execution, step)
    record = scheduler.repository.task_plan_records[(execution.id, "step_a")]
    assert record.storage_key.endswith("task-plan.json")

    scheduler.runtime_controller = _FailingLaunchRuntime()
    dispatch_ir = WorkflowIR(
        schema_version=1,
        workflow_id="wf",
        steps=[step],
        dag_edges=[],
        metadata={},
    )
    await scheduler._dispatch_to_runtime(execution, dispatch_ir, step)
    assert scheduler.runtime_controller.dispatched[0]["step_id"] == "step_a"  # type: ignore[attr-defined]

    scheduler.repository.count_events = AsyncMock(return_value=100)  # type: ignore[method-assign]
    scheduler.repository.create_checkpoint = AsyncMock()  # type: ignore[method-assign]
    execution_service.get_execution_state = AsyncMock(return_value=state)  # type: ignore[method-assign]
    await scheduler._maybe_checkpoint(execution.id)
    checkpoint = scheduler.repository.create_checkpoint.await_args.args[0]
    assert checkpoint.execution_id == execution.id
    assert checkpoint.active_step_ids == ["step_a"]

    now = datetime.now(UTC)
    lease = ExecutionDispatchLease(
        execution_id=execution.id,
        step_id="step_a",
        scheduler_worker_id="worker",
        acquired_at=now - timedelta(minutes=10),
        expires_at=now - timedelta(minutes=5),
        released_at=None,
        expired=False,
    )
    await scheduler.repository.create_dispatch_lease(lease)
    retryable = await scheduler._collect_retryable_steps(
        execution,
        WorkflowIR(schema_version=1, workflow_id="wf", steps=[step], dag_edges=[]),
        state,
    )
    assert [item.step_id for item in retryable] == ["step_a"]
    assert lease.expired is True


@pytest.mark.asyncio
async def test_scheduler_approval_gate_invokes_interactions_service() -> None:
    workflow_service, execution_service, scheduler = _build_scheduler()
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Approval Helper Workflow",
            description=None,
            yaml_source=dedent("""
                schema_version: 1
                steps:
                  - id: approval_step
                    step_type: approval_gate
                    approval_config:
                      required_approvers: [ops]
            """).strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        actor_id,
    )
    execution = await execution_service.create_execution(
        ExecutionCreate(workflow_definition_id=workflow.id, workspace_id=workspace_id),
        created_by=actor_id,
    )

    interaction_calls: list[dict[str, Any]] = []

    async def _create_approval_request(**payload: Any) -> None:
        interaction_calls.append(payload)

    scheduler.interactions_service = SimpleNamespace(
        create_approval_request=_create_approval_request,
    )
    step = StepIR(
        step_id="approval_step",
        step_type="approval_gate",
        approval_config=ApprovalConfigIR(required_approvers=["ops"], timeout_seconds=1),
    )
    await scheduler._handle_approval_gate(execution, step)
    await scheduler._handle_approval_gate(
        execution,
        StepIR(step_id="skip", step_type="approval_gate"),
    )

    approval_wait = await scheduler.repository.get_approval_wait(execution.id, "approval_step")
    assert approval_wait is not None
    assert approval_wait.timeout_action is ApprovalTimeoutAction.fail
    assert interaction_calls[0]["step_id"] == "approval_step"
