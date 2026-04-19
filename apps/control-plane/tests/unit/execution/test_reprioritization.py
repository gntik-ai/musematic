from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import ValidationError
from platform.execution.models import Execution, ExecutionStatus
from platform.execution.reprioritization import ReprioritizationService
from platform.execution.schemas import ReprioritizationTriggerCreate, ReprioritizationTriggerUpdate
from platform.workflows.models import TriggerType
from uuid import uuid4

import pytest

from tests.workflow_execution_support import FakeExecutionRepository


def _execution(
    *, workspace_id, step: str, created_at: datetime, sla_deadline: datetime
) -> Execution:
    execution = Execution(
        workflow_version_id=uuid4(),
        workflow_definition_id=uuid4(),
        trigger_type=TriggerType.manual,
        status=ExecutionStatus.queued,
        input_parameters={},
        workspace_id=workspace_id,
        correlation_workspace_id=workspace_id,
        sla_deadline=sla_deadline,
    )
    execution.id = uuid4()
    execution.created_at = created_at
    execution.updated_at = created_at
    execution.step_hint = step  # type: ignore[attr-defined]
    return execution


@pytest.mark.asyncio
async def test_reprioritization_trigger_crud_and_validation() -> None:
    workspace_id = uuid4()
    service = ReprioritizationService(repository=FakeExecutionRepository())

    created = await service.create_trigger(
        ReprioritizationTriggerCreate(
            workspace_id=workspace_id,
            name="SLA pressure",
            condition_config={"threshold_fraction": 0.15},
        ),
        created_by=uuid4(),
    )
    listed, total = await service.list_triggers(workspace_id)
    fetched = await service.get_trigger(created.id, workspace_id)
    updated = await service.update_trigger(
        created.id,
        ReprioritizationTriggerUpdate(priority_rank=5, enabled=False),
        workspace_id=workspace_id,
    )

    assert total == 1
    assert listed[0].id == created.id
    assert fetched.id == created.id
    assert updated.priority_rank == 5
    assert updated.enabled is False

    await service.delete_trigger(created.id, workspace_id=workspace_id)
    listed, total = await service.list_triggers(workspace_id)
    assert listed == []
    assert total == 0

    with pytest.raises(ValidationError) as invalid_threshold:
        await service.create_trigger(
            ReprioritizationTriggerCreate(
                workspace_id=workspace_id,
                name="bad",
                condition_config={"threshold_fraction": 1.1},
            ),
            created_by=None,
        )
    assert invalid_threshold.value.code == "REPRIORITIZATION_TRIGGER_INVALID"

    with pytest.raises(ValidationError) as invalid_type:
        await service.create_trigger(
            ReprioritizationTriggerCreate(
                workspace_id=workspace_id,
                name="bad-type",
                trigger_type="custom",
                condition_config={"threshold_fraction": 0.1},
            ),
            created_by=None,
        )
    assert invalid_type.value.code == "REPRIORITIZATION_TRIGGER_UNSUPPORTED"


@pytest.mark.asyncio
async def test_reprioritization_evaluates_sla_and_is_idempotent() -> None:
    workspace_id = uuid4()
    repository = FakeExecutionRepository()
    service = ReprioritizationService(repository=repository)
    await service.create_trigger(
        ReprioritizationTriggerCreate(
            workspace_id=workspace_id,
            name="Urgent first",
            condition_config={"threshold_fraction": 0.2},
        ),
        created_by=None,
    )

    now = datetime.now(UTC)
    relaxed = _execution(
        workspace_id=workspace_id,
        step="relaxed",
        created_at=now - timedelta(minutes=1),
        sla_deadline=now + timedelta(minutes=29),
    )
    urgent = _execution(
        workspace_id=workspace_id,
        step="urgent",
        created_at=now - timedelta(minutes=9),
        sla_deadline=now + timedelta(minutes=1),
    )

    result = await service.evaluate_for_dispatch_cycle([relaxed, urgent], workspace_id, 100)
    assert [item.id for item in result.ordered_executions] == [urgent.id, relaxed.id]
    assert len(result.firings) == 1
    assert result.firings[0].old_position == 2
    assert result.firings[0].new_position == 1
    assert result.timed_out is False

    already_sorted = await service.evaluate_for_dispatch_cycle([urgent, relaxed], workspace_id, 100)
    assert [item.id for item in already_sorted.ordered_executions] == [urgent.id, relaxed.id]
    assert already_sorted.firings == []


@pytest.mark.asyncio
async def test_reprioritization_budget_timeout_returns_original_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid4()
    repository = FakeExecutionRepository()
    service = ReprioritizationService(repository=repository)
    await service.create_trigger(
        ReprioritizationTriggerCreate(
            workspace_id=workspace_id,
            name="Urgent first",
            condition_config={"threshold_fraction": 0.5},
        ),
        created_by=None,
    )
    now = datetime.now(UTC)
    executions = [
        _execution(
            workspace_id=workspace_id,
            step=f"step-{index}",
            created_at=now - timedelta(minutes=10),
            sla_deadline=now + timedelta(seconds=30 + index),
        )
        for index in range(2)
    ]
    values = iter([0.0, 1.0])
    monkeypatch.setattr("platform.execution.reprioritization.monotonic", lambda: next(values))

    result = await service.evaluate_for_dispatch_cycle(executions, workspace_id, cycle_budget_ms=0)

    assert result.timed_out is True
    assert result.firings == []
    assert [item.id for item in result.ordered_executions] == [item.id for item in executions]
