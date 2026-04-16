from __future__ import annotations

import sys
from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.exceptions import ValidationError
from platform.simulation.comparison import analyzer as comparison
from platform.simulation.comparison.analyzer import ComparisonAnalyzer
from platform.simulation.coordination.runner import SimulationRunner, _field
from platform.simulation.exceptions import (
    IncompatibleComparisonError,
    SimulationInfrastructureUnavailableError,
    SimulationNotFoundError,
)
from platform.simulation.isolation.enforcer import IsolationEnforcer
from platform.simulation.models import BehavioralPrediction, SimulationComparisonReport
from platform.simulation.prediction import forecaster as prediction
from platform.simulation.prediction.forecaster import BehavioralForecaster
from platform.simulation.repository import SimulationRepository
from platform.simulation.router import _workspace_id
from platform.simulation.schemas import (
    BehavioralPredictionCreateRequest,
    DigitalTwinResponse,
    SimulationComparisonCreateRequest,
    SimulationRunCreateRequest,
)
from platform.simulation.service import SimulationService
from platform.simulation.twins.snapshot import TwinSnapshotService, _apply_modification, _dump
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from tests.unit.simulation.test_behavioral_forecaster import (
    FakeClickHouse,
    _rows,
    _twin,
)
from tests.unit.simulation.test_behavioral_forecaster import (
    FakePublisher as PredictionPublisher,
)
from tests.unit.simulation.test_behavioral_forecaster import (
    FakeRepository as PredictionRepository,
)
from tests.unit.simulation.test_comparison_analyzer import (
    FakePublisher as ComparisonPublisher,
)
from tests.unit.simulation.test_comparison_analyzer import (
    FakeRepository as ComparisonRepository,
)
from tests.unit.simulation.test_comparison_analyzer import (
    _report,
    _run,
)
from tests.unit.simulation.test_service import FakeEnforcer, FakeRunner, FakeTwinSnapshot, _policy
from tests.unit.simulation.test_service import FakeRepository as ServiceRepository
from tests.unit.simulation.test_simulation_runner import (
    FakePublisher as RunnerPublisher,
)
from tests.unit.simulation.test_simulation_runner import (
    FakeRepository as RunnerRepository,
)


@pytest.mark.asyncio
async def test_runner_defensive_error_paths() -> None:
    repository = RunnerRepository()
    runner = SimulationRunner(
        repository=repository,
        controller_client=None,
        publisher=RunnerPublisher(),
    )
    with pytest.raises(SimulationNotFoundError):
        await runner.cancel(uuid4(), uuid4())
    with pytest.raises(SimulationInfrastructureUnavailableError):
        await runner._create_controller_run(
            workspace_id=uuid4(),
            twin_configs=[],
            scenario_config={},
            max_duration_seconds=1,
        )

    runner.controller_client = SimpleNamespace()
    with pytest.raises(SimulationInfrastructureUnavailableError):
        await runner._create_controller_run(
            workspace_id=uuid4(),
            twin_configs=[],
            scenario_config={},
            max_duration_seconds=1,
        )

    run = await repository.create_run(
        _run_for_runner(workspace_id=uuid4(), status="running", controller_run_id="ctrl")
    )
    runner.controller_client = SimpleNamespace(
        cancel_simulation=AsyncMock(side_effect=RuntimeError("down"))
    )
    with pytest.raises(SimulationInfrastructureUnavailableError):
        await runner.cancel(run.id, run.workspace_id)

    run_without_controller_id = await repository.create_run(
        _run_for_runner(workspace_id=uuid4(), status="running", controller_run_id=None)
    )
    runner.controller_client = SimpleNamespace()
    assert await runner.cancel(run_without_controller_id.id, run_without_controller_id.workspace_id)
    assert _field(SimpleNamespace(controller_run_id="object-ctrl"), "controller_run_id") == (
        "object-ctrl"
    )


@pytest.mark.asyncio
async def test_comparison_error_paths_and_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = uuid4()
    repository = ComparisonRepository()
    primary = _run(workspace_id, [uuid4()], {"quality_score": [1.0]})
    report = _report(primary.id)
    repository.runs = {primary.id: primary}
    repository.reports = {report.id: report}
    analyzer = ComparisonAnalyzer(
        repository=repository,
        clickhouse_client=None,
        publisher=ComparisonPublisher(),
        settings=PlatformSettings(),
    )

    with pytest.raises(IncompatibleComparisonError):
        await analyzer.analyze(report=report, workspace_id=workspace_id)
    missing_primary = _report(uuid4(), uuid4())
    with pytest.raises(SimulationNotFoundError):
        await analyzer.analyze(report=missing_primary, workspace_id=workspace_id)
    secondary_missing = _report(primary.id, uuid4())
    with pytest.raises(SimulationNotFoundError):
        await analyzer.analyze(report=secondary_missing, workspace_id=workspace_id)

    prediction_report = SimulationComparisonReport(
        comparison_type="prediction_vs_actual",
        primary_run_id=primary.id,
        metric_differences=[],
        status="pending",
        compatible=True,
        incompatibility_reasons=[],
    )
    prediction_report.id = uuid4()
    with pytest.raises(IncompatibleComparisonError):
        await analyzer.analyze(report=prediction_report, workspace_id=workspace_id)
    prediction_report.prediction_id = uuid4()
    with pytest.raises(SimulationNotFoundError):
        await analyzer.analyze(report=prediction_report, workspace_id=workspace_id)

    assert comparison._metric_series({"execution_metrics": [{"x": 1.0}, "bad", {"x": 2}]}) == {
        "x": [1.0, 2.0]
    }
    assert comparison._metric_series({"metrics": {"x": 1.0}}) == {"x": [1.0]}
    assert comparison._direction("quality_score", 0.0) == "neutral"
    assert comparison._significance(0.001, 0.05) == "high"
    assert comparison._significance(0.03, 0.05) == "medium"
    assert comparison._significance(0.5, 0.05) == "low"
    assert comparison._overall_verdict([]) == "equivalent"
    assert comparison._overall_verdict([{"significance": "high", "direction": "worse"}]) == (
        "secondary_better"
    )
    assert comparison._overall_verdict(
        [
            {"significance": "high", "direction": "better"},
            {"significance": "high", "direction": "worse"},
        ]
    ) == "equivalent"
    assert comparison._predicted_values({"x": 1.0}) == {"x": 1.0}
    assert comparison._accuracy_report({"x": 1.0}, {})["x"]["accuracy_pct"] == 0.0

    monkeypatch.setitem(sys.modules, "scipy", None)
    assert comparison._ttest_pvalue([1.0], [1.0]) == 1.0
    fake_scipy = ModuleType("scipy")
    fake_scipy.stats = SimpleNamespace(
        ttest_ind=lambda primary, secondary, equal_var: SimpleNamespace(pvalue=0.02)
    )
    monkeypatch.setitem(sys.modules, "scipy", fake_scipy)
    assert comparison._ttest_pvalue([1.0], [2.0]) == 0.02


@pytest.mark.asyncio
async def test_forecaster_error_paths_and_math_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    twin = _twin()
    repository = PredictionRepository(twin)
    forecaster = BehavioralForecaster(
        repository=repository,
        clickhouse_client=FakeClickHouse(_rows()),
        publisher=PredictionPublisher(),
        settings=PlatformSettings(),
    )
    with pytest.raises(SimulationNotFoundError):
        await forecaster.forecast(twin_id=uuid4(), workspace_id=twin.workspace_id)
    with pytest.raises(SimulationNotFoundError):
        await forecaster.forecast_prediction(uuid4())

    prediction_row = await repository.create_prediction(
        BehavioralPrediction(digital_twin_id=uuid4(), condition_modifiers={}, status="pending")
    )
    prediction_row.digital_twin = SimpleNamespace(workspace_id=twin.workspace_id)
    with pytest.raises(SimulationNotFoundError):
        await forecaster.forecast_prediction(prediction_row.id)

    monkeypatch.setitem(sys.modules, "scipy", None)
    assert prediction._linregress([0, 1], [1.0, 2.0])["r_value"] == pytest.approx(1.0)
    assert prediction._residual_std([1.0], 0.0, 1.0) == 0.0
    assert prediction._trend_from_slope(0.0, inverse=False) == "stable"
    assert prediction._confidence_level([]) == "low"
    assert prediction._confidence_level([0.5]) == "medium"
    assert prediction._confidence_level([0.1]) == "low"
    no_clickhouse = BehavioralForecaster(
        repository=repository,
        clickhouse_client=None,
        publisher=PredictionPublisher(),
        settings=PlatformSettings(),
    )
    assert await no_clickhouse._load_history("agent", twin.workspace_id) == []


@pytest.mark.asyncio
async def test_snapshot_fallbacks_and_repository_cache_edges() -> None:
    service = TwinSnapshotService(
        repository=SimpleNamespace(),
        registry_service=None,
        clickhouse_client=None,
        publisher=SimpleNamespace(),
        settings=PlatformSettings(),
    )
    with pytest.raises(SimulationInfrastructureUnavailableError):
        await service._get_agent_profile("agent", uuid4())

    profile = SimpleNamespace(latest_revision_id=uuid4(), status="active")
    registry = SimpleNamespace(
        get_agent_by_fqn=AsyncMock(return_value=profile),
        get_agent_revision=AsyncMock(side_effect=[TypeError(), {"model": {"name": "m"}}]),
    )
    service.registry_service = registry
    assert await service._get_agent_profile("agent", uuid4()) is profile
    assert await service._get_agent_revision("agent", profile.latest_revision_id) == {
        "model": {"name": "m"}
    }
    service.registry_service = SimpleNamespace(resolve_fqn=AsyncMock(return_value=profile))
    assert await service._get_agent_profile("agent", uuid4()) is profile
    service.registry_service = SimpleNamespace()
    with pytest.raises(SimulationInfrastructureUnavailableError):
        await service._get_agent_profile("agent", uuid4())
    assert await service._get_agent_revision("agent", uuid4()) is None

    service.clickhouse_client = SimpleNamespace(
        execute_query=AsyncMock(side_effect=RuntimeError("down"))
    )
    summary = await service._behavioral_history_summary("agent", uuid4())
    assert summary["history_days_used"] == 0

    snapshot = {"model": "not-a-dict"}
    _apply_modification(snapshot, "model.name", "new")
    assert snapshot["model"]["name"] == "new"
    assert _dump(None) == {}
    assert _dump(SimpleNamespace(model_dump=lambda mode: {"mode": mode})) == {"mode": "json"}
    assert _dump(1) == {}

    repository = SimulationRepository(SimpleNamespace(), redis=None)
    assert await repository.get_status_cache(uuid4()) is None
    await repository.set_status_cache(uuid4(), {"status": "running"})


@pytest.mark.asyncio
async def test_remaining_service_event_isolation_repository_and_schema_branches() -> None:
    workspace_id = uuid4()
    twin = _twin()
    twin.workspace_id = workspace_id
    run = _run_for_runner(workspace_id, "completed")
    policy = _policy(workspace_id)
    repository = ServiceRepository(run, twin, policy)
    service = SimulationService(
        repository=repository,
        settings=PlatformSettings(),
        runner=FakeRunner(run),
        twin_snapshot=FakeTwinSnapshot(twin),
        isolation_enforcer=FakeEnforcer(),
        forecaster=SimpleNamespace(),
        comparison_analyzer=SimpleNamespace(
            analyze=AsyncMock(side_effect=IncompatibleComparisonError(["bad"]))
        ),
        events_consumer=SimpleNamespace(),
        prediction_worker=SimpleNamespace(),
    )

    with pytest.raises(SimulationNotFoundError):
        await service.get_simulation_run(uuid4(), workspace_id)
    assert await service.get_simulation_summary(uuid4(), workspace_id) is None
    assert await service.get_twin_config(uuid4(), workspace_id) is None
    with pytest.raises(SimulationNotFoundError):
        await service.get_isolation_policy(uuid4(), workspace_id)
    with pytest.raises(SimulationNotFoundError):
        await service.get_behavioral_prediction(uuid4(), workspace_id)
    with pytest.raises(SimulationNotFoundError):
        await service.get_comparison_report(uuid4(), workspace_id)
    with pytest.raises(SimulationNotFoundError):
        await service._twin_or_raise(uuid4(), workspace_id)
    with pytest.raises(SimulationNotFoundError):
        await service._run_or_raise(uuid4(), workspace_id)
    with pytest.raises(IncompatibleComparisonError):
        await service.create_comparison_report(
            run.id,
            SimulationComparisonCreateRequest(
                workspace_id=workspace_id,
                comparison_type="simulation_vs_simulation",
                secondary_run_id=run.id,
            ),
        )

    from platform.simulation.events import (
        SimulationEventPublisher,
        SimulationEventsConsumer,
        _payload_uuid,
    )

    await SimulationEventPublisher(None).publish(
        "simulation_run_created",
        key_id=uuid4(),
        workspace_id=workspace_id,
    )
    assert _payload_uuid({}, "missing") is None
    assert _payload_uuid({"id": uuid4()}, "id") is not None
    async_released: list[object] = []

    async def _release(item):
        async_released.append(item)

    consumer = SimulationEventsConsumer(FakeEventRepository(run), release_isolation=_release)
    await consumer.handle_event(
        SimpleNamespace(
            event_type="simulation_run_failed",
            payload={"run_id": str(run.id), "workspace_id": str(workspace_id)},
        )
    )
    assert async_released == [run]

    enforcer = IsolationEnforcer(
        repository=SimpleNamespace(set_run_isolation_bundle=AsyncMock()),
        policy_service=SimpleNamespace(),
        runner=None,
        publisher=SimpleNamespace(isolation_breach_detected=AsyncMock()),
        settings=PlatformSettings(),
    )
    assert await enforcer.apply(run, policy) is None
    run.isolation_policy_id = uuid4()
    assert await enforcer.apply_default_strict(run) is None
    run.isolation_bundle_fingerprint = None
    await enforcer.release(run)

    assert _workspace_id({"workspace_id": str(workspace_id)}, None) == workspace_id
    with pytest.raises(ValidationError):
        _workspace_id({}, None)
    with pytest.raises(PydanticValidationError):
        SimulationRunCreateRequest(
            workspace_id=workspace_id,
            name="scenario",
            digital_twin_ids=[twin.id],
            scenario_config={"duration_seconds": 0},
        )
    with pytest.raises(PydanticValidationError):
        BehavioralPredictionCreateRequest(
            workspace_id=workspace_id,
            condition_modifiers={"load_factor": 0},
        )
    with pytest.raises(PydanticValidationError):
        SimulationComparisonCreateRequest(
            workspace_id=workspace_id,
            comparison_type="prediction_vs_actual",
        )
    response = DigitalTwinResponse(
        twin_id=twin.id,
        workspace_id=workspace_id,
        source_agent_fqn="agent",
        source_revision_id=None,
        version=1,
        parent_twin_id=None,
        config_snapshot={},
        behavioral_history_summary={"warning_flags": ["archived"]},
        modifications=[],
        is_active=True,
        created_at=datetime.now(UTC),
        warning_flags=["explicit"],
    )
    assert response.warning_flags == ["explicit"]


class FakeEventRepository:
    def __init__(self, run):
        self.run = run

    async def update_run_status(self, run_id, workspace_id, status, *, results=None):
        del run_id, workspace_id, results
        self.run.status = status
        return self.run

    async def set_status_cache(self, run_id, status_dict):
        del run_id, status_dict


def _run_for_runner(workspace_id, status: str, controller_run_id: str | None = None):
    from platform.simulation.models import SimulationRun

    run = SimulationRun(
        workspace_id=workspace_id,
        name="scenario",
        digital_twin_ids=[],
        scenario_config={},
        status=status,
        controller_run_id=controller_run_id,
        initiated_by=uuid4(),
    )
    run.id = uuid4()
    run.created_at = datetime.now(UTC)
    return run
