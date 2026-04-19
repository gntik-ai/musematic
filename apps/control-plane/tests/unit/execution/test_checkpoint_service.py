from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.execution.checkpoint_service import CheckpointService
from platform.execution.exceptions import (
    CheckpointRetentionExpiredError,
    CheckpointSizeLimitExceededError,
    RollbackFailedError,
    RollbackNotEligibleError,
)
from platform.execution.models import (
    Execution,
    ExecutionCheckpoint,
    ExecutionEventType,
    ExecutionStatus,
    RollbackActionStatus,
)
from platform.execution.projector import ExecutionProjector
from platform.execution.schemas import DEFAULT_CHECKPOINT_POLICY, ExecutionStateResponse
from platform.workflows.ir import StepIR
from platform.workflows.models import TriggerType
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from tests.workflow_execution_support import FakeExecutionRepository, FakeProducer, make_settings


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
            "step_results": number,
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


def _service(
    max_size: int = 10_485_760,
) -> tuple[CheckpointService, FakeExecutionRepository, FakeProducer]:
    repository = FakeExecutionRepository()
    producer = FakeProducer()
    settings = make_settings().model_copy(update={"checkpoint_max_size_bytes": max_size})
    return (
        CheckpointService(
            repository=repository,
            settings=settings,
            producer=producer,
            projector=ExecutionProjector(),
        ),
        repository,
        producer,
    )


@pytest.mark.parametrize(
    ("step", "policy", "expected"),
    [
        (StepIR(step_id="tool", step_type="tool_call"), {"type": "before_tool_invocations"}, True),
        (
            StepIR(step_id="agent", step_type="agent_task"),
            {"type": "before_tool_invocations"},
            False,
        ),
        (StepIR(step_id="agent", step_type="agent_task"), {"type": "before_every_step"}, True),
        (
            StepIR(step_id="other", step_type="tool_call"),
            {"type": "named_steps", "step_ids": ["target"]},
            False,
        ),
        (
            StepIR(step_id="target", step_type="tool_call"),
            {"type": "named_steps", "step_ids": ["target"]},
            True,
        ),
        (StepIR(step_id="tool", step_type="tool_call"), {"type": "disabled"}, False),
    ],
)
def test_checkpoint_service_should_capture(
    step: StepIR, policy: dict[str, object], expected: bool
) -> None:
    service, _, _ = _service()
    assert service.should_capture(step, policy) is expected


@pytest.mark.asyncio
async def test_checkpoint_service_capture_assigns_numbers_and_serializes_state() -> None:
    service, repository, _ = _service()
    execution = _execution()
    await repository.create_execution(execution)
    state = ExecutionStateResponse(
        execution_id=execution.id,
        status=ExecutionStatus.running,
        completed_step_ids=["step-a"],
        active_step_ids=["step-b"],
        pending_step_ids=["step-b", "step-c"],
        step_results={
            "_execution_data": {"cursor": "b"},
            "_accumulated_costs": {"usd": 12.5},
            "step-a": {"ok": True},
        },
        last_event_sequence=7,
        workflow_version_id=execution.workflow_version_id,
    )

    first = await service.capture(
        execution=execution,
        step_id="step-b",
        state=state,
        policy_snapshot={"type": "before_every_step"},
    )
    second = await service.capture(
        execution=execution,
        step_id="step-c",
        state=state,
        policy_snapshot={"type": "before_every_step"},
    )

    assert first.checkpoint_number == 1
    assert second.checkpoint_number == 2
    assert first.current_context == {"cursor": "b"}
    assert first.accumulated_costs == {"usd": 12.5}
    assert first.policy_snapshot == {"type": "before_every_step"}


@pytest.mark.asyncio
async def test_checkpoint_service_capture_rejects_oversized_payloads() -> None:
    service, repository, _ = _service(max_size=64)
    execution = _execution()
    await repository.create_execution(execution)
    state = ExecutionStateResponse(
        execution_id=execution.id,
        status=ExecutionStatus.running,
        completed_step_ids=[],
        active_step_ids=["step-a"],
        pending_step_ids=["step-a"],
        step_results={"blob": "x" * 1024},
        last_event_sequence=1,
        workflow_version_id=execution.workflow_version_id,
    )

    with pytest.raises(CheckpointSizeLimitExceededError):
        await service.capture(
            execution=execution,
            step_id="step-a",
            state=state,
            policy_snapshot=None,
        )


@pytest.mark.asyncio
async def test_checkpoint_service_rollback_restores_state_and_marks_superseded() -> None:
    service, repository, producer = _service()
    execution = _execution(status=ExecutionStatus.failed)
    await repository.create_execution(execution)
    checkpoints = [
        _checkpoint(
            execution_id=execution.id,
            number=1,
            completed=[],
            pending=["step-a", "step-b", "step-c"],
            costs={"usd": 10.0},
        ),
        _checkpoint(
            execution_id=execution.id,
            number=2,
            completed=["step-a"],
            pending=["step-b", "step-c"],
            costs={"usd": 20.0},
        ),
        _checkpoint(
            execution_id=execution.id,
            number=3,
            completed=["step-a", "step-b"],
            pending=["step-c"],
            costs={"usd": 35.0},
        ),
    ]
    for item in checkpoints:
        await repository.create_checkpoint(item)

    response = await service.rollback(
        execution.id,
        2,
        initiated_by=uuid4(),
        reason="bad output",
    )

    assert response.execution_status is ExecutionStatus.rolled_back
    assert response.target_checkpoint_number == 2
    assert response.cost_delta_reversed == {"usd": 15.0}
    assert repository.rollback_actions[-1].status is RollbackActionStatus.completed
    assert repository.checkpoints[execution.id][-1].superseded is True
    events = await repository.get_events(execution.id)
    assert events[-1].event_type is ExecutionEventType.rolled_back
    assert any(message["event_type"] == "execution.rolled_back" for message in producer.messages)


@pytest.mark.asyncio
async def test_checkpoint_service_rollback_rejects_ineligible_and_expired_checkpoints() -> None:
    service, repository, _ = _service()
    execution = _execution(status=ExecutionStatus.running)
    await repository.create_execution(execution)
    expired = _checkpoint(
        execution_id=execution.id,
        number=1,
        completed=[],
        pending=["step-a"],
        costs={"usd": 1.0},
    )
    await repository.create_checkpoint(expired)
    expired.created_at = datetime.now(UTC) - timedelta(days=365)
    expired.updated_at = expired.created_at

    with pytest.raises(RollbackNotEligibleError):
        await service.rollback(execution.id, 1, initiated_by=None, reason=None)

    execution.status = ExecutionStatus.failed
    with pytest.raises(CheckpointRetentionExpiredError):
        await service.rollback(execution.id, 1, initiated_by=None, reason=None)


@pytest.mark.asyncio
async def test_checkpoint_service_rollback_failure_quarantines_execution() -> None:
    service, repository, _ = _service()
    execution = _execution(status=ExecutionStatus.failed)
    await repository.create_execution(execution)
    checkpoint = _checkpoint(
        execution_id=execution.id,
        number=1,
        completed=[],
        pending=["step-a"],
        costs={"usd": 1.0},
    )
    await repository.create_checkpoint(checkpoint)
    repository.mark_superseded_after = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

    with pytest.raises(RollbackFailedError):
        await service.rollback(execution.id, 1, initiated_by=None, reason="boom")

    assert execution.status is ExecutionStatus.rollback_failed
    assert repository.rollback_actions[-1].status is RollbackActionStatus.failed


@pytest.mark.asyncio
async def test_checkpoint_service_gc_expired_returns_deleted_count() -> None:
    service, repository, _ = _service()
    deleted = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]

    class _Result:
        def __init__(self, values):
            self.values = values

        def scalars(self):
            return self

        def all(self):
            return list(self.values)

    repository.session.execute = AsyncMock(return_value=_Result(deleted))  # type: ignore[method-assign]
    repository.session.delete = AsyncMock()  # type: ignore[method-assign]
    repository.session.flush = AsyncMock()  # type: ignore[method-assign]

    count = await service.gc_expired(retention_days=30)

    assert count == 2
    assert repository.session.delete.await_count == 2
