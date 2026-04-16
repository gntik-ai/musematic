from __future__ import annotations

from datetime import UTC, datetime
from platform.simulation.models import (
    BehavioralPrediction,
    DigitalTwin,
    SimulationComparisonReport,
    SimulationIsolationPolicy,
    SimulationRun,
)
from platform.simulation.repository import SimulationRepository
from uuid import uuid4

import pytest


class FakeScalarResult:
    def __init__(self, value=None, values=None) -> None:
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.values


class FakeSession:
    def __init__(self) -> None:
        self.results: list[FakeScalarResult] = []
        self.added: list[object] = []
        self.flushed = 0

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed += 1

    async def execute(self, statement):
        del statement
        return self.results.pop(0) if self.results else FakeScalarResult()


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttl: int | None = None

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self.values[key] = value
        self.ttl = ttl

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)


def _run() -> SimulationRun:
    run = SimulationRun(
        workspace_id=uuid4(),
        name="scenario",
        digital_twin_ids=[],
        scenario_config={},
        status="provisioning",
        initiated_by=uuid4(),
    )
    run.id = uuid4()
    run.created_at = datetime.now(UTC)
    run.updated_at = run.created_at
    return run


def _twin(workspace_id=None) -> DigitalTwin:
    twin = DigitalTwin(
        workspace_id=workspace_id or uuid4(),
        source_agent_fqn="namespace.agent",
        source_revision_id=None,
        version=1,
        config_snapshot={},
        behavioral_history_summary={},
        modifications=[],
        is_active=True,
    )
    twin.id = uuid4()
    twin.created_at = datetime.now(UTC)
    return twin


@pytest.mark.asyncio
async def test_repository_run_crud_and_status_cache() -> None:
    session = FakeSession()
    redis = FakeRedis()
    repository = SimulationRepository(session, redis)
    run = _run()

    assert await repository.create_run(run) is run
    session.results = [FakeScalarResult(value=run)]
    assert await repository.get_run(run.id, run.workspace_id) is run

    extra = _run()
    session.results = [FakeScalarResult(values=[run, extra])]
    items, cursor = await repository.list_runs(
        run.workspace_id,
        status="provisioning",
        limit=1,
        cursor=str(uuid4()),
    )
    assert items == [run]
    assert cursor == str(run.id)

    session.results = [FakeScalarResult(), FakeScalarResult(value=run)]
    updated = await repository.update_run_status(
        run.id,
        run.workspace_id,
        "completed",
        results={"ok": True},
    )
    assert updated is run
    assert session.flushed >= 2

    session.results = [FakeScalarResult(), FakeScalarResult(value=run)]
    assert await repository.set_run_isolation_bundle(run.id, run.workspace_id, "fp") is run

    await repository.set_status_cache(run.id, {"status": "completed"})
    cached = await repository.get_status_cache(run.id)
    assert cached["status"] == "completed"
    assert redis.ttl == 24 * 60 * 60


@pytest.mark.asyncio
async def test_repository_twin_policy_prediction_and_report_methods() -> None:
    session = FakeSession()
    repository = SimulationRepository(session)
    twin = _twin()
    policy = SimulationIsolationPolicy(
        workspace_id=twin.workspace_id,
        name="strict",
        blocked_actions=[],
        stubbed_actions=[],
        permitted_read_sources=[],
        is_default=True,
        halt_on_critical_breach=True,
    )
    policy.id = uuid4()
    prediction = BehavioralPrediction(
        digital_twin_id=twin.id,
        condition_modifiers={},
        status="pending",
    )
    prediction.id = uuid4()
    report = SimulationComparisonReport(
        comparison_type="simulation_vs_simulation",
        primary_run_id=uuid4(),
        metric_differences=[],
        status="pending",
        compatible=True,
        incompatibility_reasons=[],
    )
    report.id = uuid4()

    assert await repository.create_twin(twin) is twin
    session.results = [FakeScalarResult(value=twin)]
    assert await repository.get_twin(twin.id, twin.workspace_id) is twin
    session.results = [FakeScalarResult(values=[twin])]
    twins, _ = await repository.list_twins(twin.workspace_id, agent_fqn="namespace.agent")
    assert twins == [twin]
    session.results = [FakeScalarResult(values=[twin])]
    assert await repository.list_twin_versions(twin) == [twin]
    await repository.update_twin_active(twin.id, twin.workspace_id, False)

    assert await repository.create_isolation_policy(policy) is policy
    session.results = [FakeScalarResult(value=policy)]
    assert await repository.get_isolation_policy(policy.id, twin.workspace_id) is policy
    session.results = [FakeScalarResult(values=[policy])]
    assert await repository.list_isolation_policies(twin.workspace_id) == [policy]

    assert await repository.create_prediction(prediction) is prediction
    session.results = [FakeScalarResult(value=prediction)]
    assert await repository.get_prediction(prediction.id, twin.workspace_id) is prediction
    session.results = [FakeScalarResult(values=[prediction])]
    assert await repository.list_pending_predictions() == [prediction]
    session.results = [FakeScalarResult(), FakeScalarResult(value=prediction)]
    assert await repository.update_prediction(prediction.id, status="completed") is prediction

    assert await repository.create_comparison_report(report) is report
    session.results = [FakeScalarResult(value=report)]
    assert await repository.get_comparison_report(report.id, twin.workspace_id) is report
    session.results = [FakeScalarResult(), FakeScalarResult(value=report)]
    assert await repository.update_comparison_report(report.id, status="completed") is report
