from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.execution.models import ApprovalDecision, ExecutionEventType, ExecutionStatus
from platform.execution.repository import ExecutionRepository
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest


class _ScalarResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class _ScalarsResult:
    def __init__(self, values: list[object]) -> None:
        self.values = list(values)

    def scalars(self) -> _ScalarsResult:
        return self

    def all(self) -> list[object]:
        return list(self.values)


def _session(
    *,
    execute_results: list[object] | None = None,
    scalar_results: list[object] | None = None,
) -> Mock:
    session = Mock()
    session.add = Mock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=list(execute_results or []))
    session.scalar = AsyncMock(side_effect=list(scalar_results or []))
    return session


@pytest.mark.asyncio
async def test_execution_repository_query_methods_return_mocked_results() -> None:
    execution = SimpleNamespace(id=uuid4())
    event = SimpleNamespace(id=uuid4())
    checkpoint = SimpleNamespace(id=uuid4())
    lease = SimpleNamespace(id=uuid4())
    record = SimpleNamespace(id=uuid4())
    approval_wait = SimpleNamespace(id=uuid4())
    session = _session(
        execute_results=[
            _ScalarResult(execution),
            _ScalarsResult([execution]),
            _ScalarsResult([execution]),
            _ScalarsResult([event]),
            _ScalarResult(checkpoint),
            _ScalarResult(lease),
            _ScalarsResult([record]),
            _ScalarResult(record),
            _ScalarResult(approval_wait),
            _ScalarsResult([approval_wait]),
            _ScalarsResult([approval_wait]),
        ],
        scalar_results=[2, 4, 7],
    )
    repository = ExecutionRepository(session)  # type: ignore[arg-type]

    assert await repository.get_execution_by_id(uuid4()) is execution
    items, total = await repository.list_executions(
        workspace_id=uuid4(),
        workflow_id=uuid4(),
        status=ExecutionStatus.running,
        trigger_type=None,
        goal_id=uuid4(),
        since=datetime.now(UTC) - timedelta(minutes=5),
        offset=3,
        limit=5,
    )
    assert items == [execution]
    assert total == 2
    assert await repository.list_by_statuses([ExecutionStatus.queued]) == [execution]
    assert await repository.count_active_for_trigger(uuid4()) == 4
    assert await repository.get_events(
        uuid4(),
        since_sequence=2,
        event_type=ExecutionEventType.completed,
    ) == [event]
    assert await repository.count_events(uuid4()) == 7
    assert await repository.get_latest_checkpoint(uuid4()) is checkpoint
    assert await repository.get_active_dispatch_lease(uuid4(), "step-a") is lease
    assert await repository.list_task_plan_records(uuid4()) == [record]
    assert await repository.get_task_plan_record(uuid4(), "step-a") is record
    assert await repository.get_approval_wait(uuid4(), "step-a") is approval_wait
    assert await repository.list_approval_waits(uuid4()) == [approval_wait]
    assert await repository.list_pending_approval_waits(datetime.now(UTC)) == [approval_wait]


@pytest.mark.asyncio
async def test_execution_repository_mutation_methods_update_state_and_flush() -> None:
    session = _session()
    repository = ExecutionRepository(session)  # type: ignore[arg-type]

    execution = SimpleNamespace(
        status=ExecutionStatus.queued,
        started_at=None,
        completed_at=None,
    )
    created_execution = await repository.create_execution(execution)  # type: ignore[arg-type]
    updated_execution = await repository.update_execution_status(
        execution,  # type: ignore[arg-type]
        ExecutionStatus.completed,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )

    repository.count_events = AsyncMock(return_value=1)  # type: ignore[method-assign]
    execution_id = uuid4()
    event = await repository.append_event(
        execution_id=execution_id,
        event_type=ExecutionEventType.created,
        step_id="step-a",
        agent_fqn="agents.alpha",
        payload={"status": "queued"},
        correlation_workspace_id=uuid4(),
        correlation_execution_id=execution_id,
    )

    checkpoint = SimpleNamespace(id=uuid4())
    lease = SimpleNamespace(released_at=None, expired=False)
    created_checkpoint = await repository.create_checkpoint(checkpoint)  # type: ignore[arg-type]
    created_lease = await repository.create_dispatch_lease(lease)  # type: ignore[arg-type]
    released_lease = await repository.release_dispatch_lease(
        lease,  # type: ignore[arg-type]
        released_at=datetime.now(UTC),
        expired=True,
    )

    created_record = SimpleNamespace(
        execution_id=uuid4(),
        step_id="step-a",
        selected_agent_fqn="agents.alpha",
        selected_tool_fqn=None,
        rationale_summary="initial",
        considered_agents_count=1,
        considered_tools_count=0,
        rejected_alternatives_count=0,
        parameter_sources=["input"],
        storage_key="plans/a.json",
        storage_size_bytes=10,
    )
    repository.get_task_plan_record = AsyncMock(return_value=None)  # type: ignore[method-assign]
    inserted_record = await repository.upsert_task_plan_record(
        created_record  # type: ignore[arg-type]
    )

    existing_record = SimpleNamespace(
        execution_id=created_record.execution_id,
        step_id="step-a",
        selected_agent_fqn=None,
        selected_tool_fqn=None,
        rationale_summary=None,
        considered_agents_count=0,
        considered_tools_count=0,
        rejected_alternatives_count=0,
        parameter_sources=[],
        storage_key="",
        storage_size_bytes=None,
    )
    updated_record = SimpleNamespace(
        execution_id=created_record.execution_id,
        step_id="step-a",
        selected_agent_fqn=None,
        selected_tool_fqn="tools.alpha",
        rationale_summary="updated",
        considered_agents_count=0,
        considered_tools_count=1,
        rejected_alternatives_count=1,
        parameter_sources=["memory"],
        storage_key="plans/b.json",
        storage_size_bytes=21,
    )
    repository.get_task_plan_record = AsyncMock(return_value=existing_record)  # type: ignore[method-assign]
    upserted_existing = await repository.upsert_task_plan_record(
        updated_record  # type: ignore[arg-type]
    )

    approval_wait = SimpleNamespace(
        decision=None,
        decided_by=None,
        decided_at=None,
    )
    created_wait = await repository.create_approval_wait(approval_wait)  # type: ignore[arg-type]
    updated_wait = await repository.update_approval_wait(
        approval_wait,  # type: ignore[arg-type]
        decision=ApprovalDecision.approved,
        decided_by="ops",
        decided_at=datetime.now(UTC),
    )

    compensation = SimpleNamespace(id=uuid4())
    created_compensation = await repository.create_compensation_record(
        compensation  # type: ignore[arg-type]
    )

    assert created_execution is execution
    assert updated_execution.status is ExecutionStatus.completed
    assert event.sequence == 2
    assert event.agent_fqn == "agents.alpha"
    assert created_checkpoint is checkpoint
    assert created_lease is lease
    assert released_lease.expired is True
    assert inserted_record is created_record
    assert upserted_existing is existing_record
    assert existing_record.selected_tool_fqn == "tools.alpha"
    assert existing_record.storage_key == "plans/b.json"
    assert created_wait is approval_wait
    assert updated_wait.decision is ApprovalDecision.approved
    assert created_compensation is compensation
    assert session.add.call_count == 7
    assert session.flush.await_count >= 8


@pytest.mark.asyncio
async def test_execution_repository_reasoning_trace_record_queries_and_upserts() -> None:
    record = SimpleNamespace(id=uuid4(), execution_id=uuid4(), step_id="trace-step")
    session = _session(execute_results=[_ScalarResult(record), _ScalarResult(None)])
    repository = ExecutionRepository(session)  # type: ignore[arg-type]

    fetched = await repository.get_reasoning_trace_record(record.execution_id, record.step_id)
    assert fetched is record

    new_record = SimpleNamespace(
        execution_id=uuid4(),
        step_id="trace-step",
        technique="DEBATE",
        storage_key="reasoning-debates/a/trace.json",
        step_count=2,
        status="complete",
        compute_budget_used=0.4,
        consensus_reached=True,
        stabilized=None,
        degradation_detected=None,
        compute_budget_exhausted=False,
        effective_budget_scope="step",
    )
    inserted = await repository.upsert_reasoning_trace_record(new_record)  # type: ignore[arg-type]

    assert inserted is new_record
    assert session.add.call_count == 1
    assert session.flush.await_count == 1


@pytest.mark.asyncio
async def test_execution_repository_updates_existing_reasoning_trace_record() -> None:
    existing_record = SimpleNamespace(
        execution_id=uuid4(),
        step_id="trace-step",
        technique="COT",
        storage_key="old.json",
        step_count=1,
        status="in_progress",
        compute_budget_used=0.1,
        consensus_reached=None,
        stabilized=None,
        degradation_detected=None,
        compute_budget_exhausted=False,
        effective_budget_scope="workflow",
    )
    updated_record = SimpleNamespace(
        execution_id=existing_record.execution_id,
        step_id=existing_record.step_id,
        technique="DEBATE",
        storage_key="new.json",
        step_count=3,
        status="complete",
        compute_budget_used=0.6,
        consensus_reached=True,
        stabilized=False,
        degradation_detected=False,
        compute_budget_exhausted=True,
        effective_budget_scope="step",
    )
    session = _session()
    repository = ExecutionRepository(session)  # type: ignore[arg-type]
    repository.get_reasoning_trace_record = AsyncMock(return_value=existing_record)  # type: ignore[method-assign]

    result = await repository.upsert_reasoning_trace_record(updated_record)  # type: ignore[arg-type]

    assert result is existing_record
    assert existing_record.technique == "DEBATE"
    assert existing_record.storage_key == "new.json"
    assert existing_record.compute_budget_exhausted is True
    assert existing_record.effective_budget_scope == "step"
    assert session.add.call_count == 0
    assert session.flush.await_count == 1
