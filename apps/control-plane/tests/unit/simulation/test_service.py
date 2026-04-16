from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.simulation.models import (
    BehavioralPrediction,
    DigitalTwin,
    SimulationComparisonReport,
    SimulationIsolationPolicy,
    SimulationRun,
)
from platform.simulation.schemas import (
    BehavioralPredictionCreateRequest,
    DigitalTwinCreateRequest,
    DigitalTwinModification,
    DigitalTwinModifyRequest,
    SimulationComparisonCreateRequest,
    SimulationIsolationPolicyCreateRequest,
    SimulationRunCreateRequest,
)
from platform.simulation.service import SimulationService
from types import SimpleNamespace
from uuid import uuid4

import pytest


class FakeRepository:
    def __init__(self, run: SimulationRun, twin: DigitalTwin, policy: SimulationIsolationPolicy):
        self.run = run
        self.twin = twin
        self.policy = policy
        self.prediction = _prediction(twin.id)
        self.report = _report(run.id)

    async def get_twin(self, twin_id, workspace_id):
        if twin_id == self.twin.id and workspace_id == self.twin.workspace_id:
            return self.twin
        return None

    async def list_twins(self, workspace_id, **kwargs):
        del kwargs
        return ([self.twin], None) if workspace_id == self.twin.workspace_id else ([], None)

    async def list_twin_versions(self, twin):
        return [twin]

    async def get_run(self, run_id, workspace_id):
        return self.run if run_id == self.run.id and workspace_id == self.run.workspace_id else None

    async def list_runs(self, workspace_id, **kwargs):
        del kwargs
        return ([self.run], None) if workspace_id == self.run.workspace_id else ([], None)

    async def create_isolation_policy(self, policy):
        policy.id = uuid4()
        policy.created_at = datetime.now(UTC)
        policy.updated_at = policy.created_at
        self.policy = policy
        return policy

    async def get_isolation_policy(self, policy_id, workspace_id):
        if policy_id == self.policy.id and workspace_id == self.policy.workspace_id:
            return self.policy
        return None

    async def list_isolation_policies(self, workspace_id):
        return [self.policy] if workspace_id == self.policy.workspace_id else []

    async def create_prediction(self, prediction):
        prediction.id = self.prediction.id
        prediction.created_at = self.prediction.created_at
        prediction.digital_twin = self.twin
        prediction.history_days_used = 0
        self.prediction = prediction
        return prediction

    async def get_prediction(self, prediction_id, workspace_id=None):
        del workspace_id
        return self.prediction if prediction_id == self.prediction.id else None

    async def create_comparison_report(self, report):
        report.id = self.report.id
        report.created_at = self.report.created_at
        self.report = report
        return report

    async def get_comparison_report(self, report_id, workspace_id):
        del workspace_id
        return self.report if report_id == self.report.id else None


class FakeRunner:
    def __init__(self, run: SimulationRun):
        self.run = run
        self.created_duration: int | None = None

    async def create(self, **kwargs):
        self.created_duration = kwargs["max_duration_seconds"]
        return self.run

    async def cancel(self, run_id, workspace_id, *, actor_id=None):
        del run_id, workspace_id, actor_id
        self.run.status = "cancelled"
        return self.run


class FakeTwinSnapshot:
    def __init__(self, twin: DigitalTwin):
        self.twin = twin

    async def create_twin(self, **kwargs):
        del kwargs
        return self.twin

    async def modify_twin(self, **kwargs):
        del kwargs
        self.twin.version += 1
        return self.twin


class FakeEnforcer:
    def __init__(self) -> None:
        self.default_applied = False
        self.applied = False
        self.released = False

    async def apply_default_strict(self, run):
        del run
        self.default_applied = True

    async def apply(self, run, policy):
        del run, policy
        self.applied = True

    async def release(self, run):
        del run
        self.released = True


class FakeAnalyzer:
    async def analyze(self, *, report, workspace_id):
        del workspace_id
        report.status = "completed"
        report.overall_verdict = "equivalent"
        return report


def _run(workspace_id, twin_id) -> SimulationRun:
    run = SimulationRun(
        workspace_id=workspace_id,
        name="scenario",
        digital_twin_ids=[str(twin_id)],
        scenario_config={},
        status="provisioning",
        initiated_by=uuid4(),
    )
    run.id = uuid4()
    run.created_at = datetime.now(UTC)
    return run


def _twin(workspace_id) -> DigitalTwin:
    twin = DigitalTwin(
        workspace_id=workspace_id,
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


def _policy(workspace_id) -> SimulationIsolationPolicy:
    policy = SimulationIsolationPolicy(
        workspace_id=workspace_id,
        name="strict",
        blocked_actions=[],
        stubbed_actions=[],
        permitted_read_sources=[],
        is_default=False,
        halt_on_critical_breach=True,
    )
    policy.id = uuid4()
    policy.created_at = datetime.now(UTC)
    policy.updated_at = policy.created_at
    return policy


def _prediction(twin_id) -> BehavioralPrediction:
    prediction = BehavioralPrediction(
        digital_twin_id=twin_id,
        condition_modifiers={},
        status="pending",
    )
    prediction.id = uuid4()
    prediction.created_at = datetime.now(UTC)
    return prediction


def _report(run_id) -> SimulationComparisonReport:
    report = SimulationComparisonReport(
        comparison_type="simulation_vs_simulation",
        primary_run_id=run_id,
        metric_differences=[],
        status="pending",
        compatible=True,
        incompatibility_reasons=[],
    )
    report.id = uuid4()
    report.created_at = datetime.now(UTC)
    return report


def _service() -> tuple[SimulationService, FakeRunner, FakeEnforcer]:
    workspace_id = uuid4()
    twin = _twin(workspace_id)
    run = _run(workspace_id, twin.id)
    policy = _policy(workspace_id)
    repository = FakeRepository(run, twin, policy)
    runner = FakeRunner(run)
    enforcer = FakeEnforcer()
    service = SimulationService(
        repository=repository,
        settings=PlatformSettings(),
        runner=runner,
        twin_snapshot=FakeTwinSnapshot(twin),
        isolation_enforcer=enforcer,
        forecaster=SimpleNamespace(),
        comparison_analyzer=FakeAnalyzer(),
        events_consumer=SimpleNamespace(),
        prediction_worker=SimpleNamespace(),
    )
    return service, runner, enforcer


@pytest.mark.asyncio
async def test_service_run_lifecycle_and_summary_methods() -> None:
    service, runner, enforcer = _service()
    workspace_id = service.repository.twin.workspace_id
    twin_id = service.repository.twin.id
    actor_id = uuid4()

    created = await service.create_simulation_run(
        SimulationRunCreateRequest(
            workspace_id=workspace_id,
            name="scenario",
            digital_twin_ids=[twin_id],
            scenario_config={"duration_seconds": 9999},
        ),
        actor_id,
    )
    assert created.run_id == service.repository.run.id
    assert runner.created_duration == 1800
    assert enforcer.default_applied is True

    cancelled = await service.cancel_simulation_run(created.run_id, workspace_id, actor_id)
    assert cancelled.status == "cancelled"
    assert enforcer.released is True
    assert (await service.get_simulation_run(created.run_id, workspace_id)).run_id == created.run_id
    runs = await service.list_simulation_runs(workspace_id, status=None, limit=10, cursor=None)
    assert runs.items
    assert (await service.get_simulation_summary(created.run_id, workspace_id)) is not None


@pytest.mark.asyncio
async def test_service_twin_policy_prediction_and_comparison_methods() -> None:
    service, _, enforcer = _service()
    workspace_id = service.repository.twin.workspace_id
    twin_id = service.repository.twin.id

    twin = await service.create_digital_twin(
        DigitalTwinCreateRequest(workspace_id=workspace_id, agent_fqn="namespace.agent")
    )
    assert twin.twin_id == twin_id
    modified = await service.modify_digital_twin(
        twin_id,
        workspace_id,
        DigitalTwinModifyRequest(
            modifications=[DigitalTwinModification(field="model.name", value="new")]
        ),
    )
    assert modified.version == 2
    assert await service.get_twin_config(twin_id, workspace_id) is not None
    assert (await service.get_digital_twin(twin_id, workspace_id)).twin_id == twin_id
    twins = await service.list_digital_twins(
        workspace_id,
        agent_fqn=None,
        is_active=None,
        limit=10,
        cursor=None,
    )
    assert twins.items
    assert (await service.list_twin_versions(twin_id, workspace_id)).total_versions == 1

    policy = await service.create_isolation_policy(
        SimulationIsolationPolicyCreateRequest(workspace_id=workspace_id, name="strict")
    )
    assert policy.name == "strict"
    policy_id = policy.policy_id
    assert (await service.get_isolation_policy(policy_id, workspace_id)).policy_id == policy_id
    assert (await service.list_isolation_policies(workspace_id)).items

    run_payload = SimulationRunCreateRequest(
        workspace_id=workspace_id,
        name="scenario",
        digital_twin_ids=[twin_id],
        scenario_config={},
        isolation_policy_id=policy_id,
    )
    await service.create_simulation_run(run_payload, uuid4())
    assert enforcer.applied is True

    prediction = await service.create_behavioral_prediction(
        twin_id,
        BehavioralPredictionCreateRequest(workspace_id=workspace_id),
    )
    assert (await service.get_behavioral_prediction(prediction.prediction_id, workspace_id)).status

    report = await service.create_comparison_report(
        service.repository.run.id,
        SimulationComparisonCreateRequest(
            workspace_id=workspace_id,
            comparison_type="simulation_vs_simulation",
            secondary_run_id=service.repository.run.id,
        ),
    )
    assert report.status == "completed"
    fetched_report = await service.get_comparison_report(report.report_id, workspace_id)
    assert fetched_report.report_id == report.report_id
