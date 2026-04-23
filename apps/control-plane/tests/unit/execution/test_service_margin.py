from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.execution.checkpoint_service import CheckpointService
from platform.execution.exceptions import (
    CheckpointNotFoundError,
    ExecutionNotFoundError,
    HotChangeIncompatibleError,
    ReprioritizationTriggerNotFoundError,
)
from platform.execution.models import Execution, ExecutionCheckpoint, ExecutionStatus
from platform.execution.projector import ExecutionProjector
from platform.execution.reprioritization import ReprioritizationService
from platform.execution.schemas import (
    DEFAULT_CHECKPOINT_POLICY,
    ExecutionCreate,
    HotChangeCompatibilityResult,
    ReprioritizationTriggerCreate,
    ReprioritizationTriggerUpdate,
    RollbackResponse,
)
from platform.execution.service import ExecutionService
from platform.workflows.models import TriggerType
from platform.workflows.schemas import WorkflowCreate
from platform.workflows.service import WorkflowService
from textwrap import dedent
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


class _CheckpointServiceStub:
    def __init__(self, **_: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    async def rollback(
        self,
        execution_id,
        checkpoint_number: int,
        *,
        initiated_by,
        reason,
    ) -> RollbackResponse:
        self.calls.append(
            {
                "execution_id": execution_id,
                "checkpoint_number": checkpoint_number,
                "initiated_by": initiated_by,
                "reason": reason,
            }
        )
        return RollbackResponse(
            rollback_action_id=uuid4(),
            execution_id=execution_id,
            target_checkpoint_id=uuid4(),
            target_checkpoint_number=checkpoint_number,
            initiated_by=initiated_by,
            cost_delta_reversed={"usd": 1.0},
            status="completed",
            execution_status=ExecutionStatus.rolled_back,
            warning="manual cleanup required",
            created_at=datetime.now(UTC),
        )


def _build_services() -> tuple[WorkflowService, ExecutionService]:
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
        object_storage=cast(Any, FakeObjectStorage()),
        runtime_controller=FakeRuntimeController(),
        reasoning_engine=None,
        context_engineering_service=None,
        projector=ExecutionProjector(),
    )
    execution_service.workflow_repository = cast(Any, workflow_repository)
    return workflow_service, execution_service


def _build_checkpoint_service() -> tuple[CheckpointService, FakeExecutionRepository]:
    repository = FakeExecutionRepository()
    service = CheckpointService(
        repository=repository,
        settings=make_settings(),
        producer=FakeProducer(),
        projector=ExecutionProjector(),
    )
    return service, repository


def _execution(*, status: ExecutionStatus = ExecutionStatus.paused) -> Execution:
    workspace_id = uuid4()
    execution = Execution(
        workflow_version_id=uuid4(),
        workflow_definition_id=uuid4(),
        trigger_type=TriggerType.manual,
        status=status,
        input_parameters={},
        workspace_id=workspace_id,
        correlation_workspace_id=workspace_id,
    )
    execution.id = uuid4()
    execution.created_at = datetime.now(UTC) - timedelta(minutes=10)
    execution.updated_at = execution.created_at
    return execution


def _checkpoint(
    *,
    execution_id,
    number: int,
    completed: list[str],
    pending: list[str],
    costs: dict[str, float],
) -> ExecutionCheckpoint:
    checkpoint = ExecutionCheckpoint(
        execution_id=execution_id,
        checkpoint_number=number,
        last_event_sequence=number,
        step_results={
            "_execution_data": {"cursor": number},
            "_accumulated_costs": costs,
        },
        completed_step_ids=completed,
        pending_step_ids=pending,
        active_step_ids=[],
        execution_data={"cursor": number},
        current_context={"cursor": number},
        accumulated_costs=costs,
        superseded=False,
        policy_snapshot=dict(DEFAULT_CHECKPOINT_POLICY),
    )
    checkpoint.id = uuid4()
    checkpoint.created_at = datetime.now(UTC) - timedelta(minutes=max(0, 4 - number))
    checkpoint.updated_at = checkpoint.created_at
    return checkpoint


@pytest.mark.asyncio
async def test_checkpoint_service_list_and_get_validate_execution_and_checkpoint_presence() -> None:
    service, repository = _build_checkpoint_service()
    execution = _execution()
    await repository.create_execution(execution)
    first = _checkpoint(
        execution_id=execution.id,
        number=1,
        completed=[],
        pending=["step-a"],
        costs={"usd": 1.0},
    )
    first.active_step_ids = ["step-live"]
    second = _checkpoint(
        execution_id=execution.id,
        number=2,
        completed=["step-a"],
        pending=["step-b"],
        costs={"usd": 2.0},
    )
    second.superseded = True
    await repository.create_checkpoint(first)
    await repository.create_checkpoint(second)

    listing = await service.list_checkpoints(
        execution.id,
        include_superseded=False,
        page=1,
        page_size=10,
    )
    detail = await service.get_checkpoint(execution.id, 2)

    assert listing.total == 1
    assert listing.items[0].current_step_id == "step-live"
    assert detail.checkpoint_number == 2
    assert detail.current_context == {"cursor": 2}
    assert detail.policy_snapshot == dict(DEFAULT_CHECKPOINT_POLICY)

    with pytest.raises(ExecutionNotFoundError):
        await service.list_checkpoints(uuid4(), include_superseded=True, page=1, page_size=10)

    with pytest.raises(CheckpointNotFoundError):
        await service.get_checkpoint(execution.id, 99)


@pytest.mark.asyncio
async def test_reprioritization_service_covers_lookup_update_and_empty_cycle_edges() -> None:
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    service = ReprioritizationService(repository=FakeExecutionRepository())

    with pytest.raises(ReprioritizationTriggerNotFoundError):
        await service.get_trigger(uuid4(), workspace_id)

    trigger = await service.create_trigger(
        ReprioritizationTriggerCreate(
            workspace_id=workspace_id,
            name="SLA pressure",
            condition_config={"threshold_fraction": 0.2},
        ),
        created_by=None,
    )

    with pytest.raises(ReprioritizationTriggerNotFoundError):
        await service.get_trigger(trigger.id, other_workspace_id)

    updated = await service.update_trigger(
        trigger.id,
        ReprioritizationTriggerUpdate(
            name="renamed",
            condition_config={"threshold_fraction": 0.1},
            action="promote_to_front",
            priority_rank=2,
            enabled=False,
        ),
        workspace_id=workspace_id,
    )
    assert updated.name == "renamed"
    assert updated.condition_config == {"threshold_fraction": 0.1}
    assert updated.priority_rank == 2
    assert updated.enabled is False

    empty_result = await service.evaluate_for_dispatch_cycle([], workspace_id, cycle_budget_ms=25)
    assert empty_result.ordered_executions == []
    assert empty_result.firings == []

    no_trigger_service = ReprioritizationService(repository=FakeExecutionRepository())
    now = datetime.now(UTC)
    execution = Execution(
        workflow_version_id=uuid4(),
        workflow_definition_id=uuid4(),
        trigger_type=TriggerType.manual,
        status=ExecutionStatus.queued,
        input_parameters={},
        workspace_id=workspace_id,
        correlation_workspace_id=workspace_id,
        sla_deadline=now + timedelta(minutes=5),
    )
    execution.id = uuid4()
    execution.created_at = now - timedelta(minutes=1)
    execution.updated_at = execution.created_at

    no_trigger_result = await no_trigger_service.evaluate_for_dispatch_cycle(
        [execution],
        workspace_id,
        cycle_budget_ms=25,
    )
    assert [item.id for item in no_trigger_result.ordered_executions] == [execution.id]
    assert no_trigger_result.firings == []

    with pytest.raises(ValidationError, match="threshold_fraction is required"):
        service._validate_condition_config("sla_approach", {})

    with pytest.raises(ValidationError, match="not supported in this release"):
        service._validate_action("demote")

    trigger.trigger_type = "other"  # type: ignore[assignment]
    assert service._evaluate_execution(execution, trigger) is None

    execution.sla_deadline = None
    assert service._evaluate_sla_approach(execution, {"threshold_fraction": 0.5}) is None

    execution.sla_deadline = execution.created_at - timedelta(seconds=1)
    assert service._evaluate_sla_approach(execution, {"threshold_fraction": 0.5}) == 0.0


@pytest.mark.asyncio
async def test_execution_service_pause_rollback_and_hot_change_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_service, execution_service = _build_services()
    actor_id = uuid4()
    workspace_id = uuid4()
    workflow = await workflow_service.create_workflow(
        WorkflowCreate(
            name="Edge Lifecycle Workflow",
            description=None,
            yaml_source=dedent("""
                schema_version: 1
                steps:
                  - id: step_a
                    step_type: tool_call
                    tool_fqn: tools.primary
                    compensation_handler: undo_step_a
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

    paused = await execution_service.pause_execution(execution.id)
    assert paused.status is ExecutionStatus.paused

    with pytest.raises(ValidationError, match="Only queued or running"):
        await execution_service.pause_execution(execution.id)

    with pytest.raises(ValidationError, match="Only completed steps"):
        await execution_service.trigger_compensation(
            execution.id,
            "step_a",
            triggered_by="ops",
        )

    monkeypatch.setattr(
        execution_service,
        "validate_hot_change",
        AsyncMock(
            return_value=HotChangeCompatibilityResult(
                compatible=False,
                issues=["schema drift"],
                active_step_ids=["step_a"],
            )
        ),
    )
    with pytest.raises(HotChangeIncompatibleError):
        await execution_service.apply_hot_change(execution.id, uuid4())

    with pytest.raises(AuthorizationError, match=r"execution\.rollback"):
        await execution_service.rollback_execution(
            execution.id,
            1,
            initiated_by=actor_id,
            authorized=False,
        )

    monkeypatch.setattr("platform.execution.service.CheckpointService", _CheckpointServiceStub)
    execution_service.checkpoint_service = None
    rolled_back = await execution_service.rollback_execution(
        execution.id,
        2,
        initiated_by=actor_id,
        reason="operator requested",
        authorized=True,
    )

    assert rolled_back.target_checkpoint_number == 2
    assert isinstance(execution_service.checkpoint_service, _CheckpointServiceStub)
