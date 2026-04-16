from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.simulation.comparison.analyzer import ComparisonAnalyzer
from platform.simulation.exceptions import IncompatibleComparisonError
from platform.simulation.models import (
    BehavioralPrediction,
    SimulationComparisonReport,
    SimulationRun,
)
from uuid import uuid4

import pytest


class FakeRepository:
    def __init__(self) -> None:
        self.runs: dict[object, SimulationRun] = {}
        self.reports: dict[object, SimulationComparisonReport] = {}
        self.predictions: dict[object, BehavioralPrediction] = {}

    async def get_run(self, run_id, workspace_id):
        run = self.runs.get(run_id)
        if run is None or run.workspace_id != workspace_id:
            return None
        return run

    async def update_comparison_report(self, report_id, **values):
        report = self.reports[report_id]
        for key, value in values.items():
            setattr(report, key, value)
        return report

    async def get_prediction(self, prediction_id, workspace_id=None):
        return self.predictions.get(prediction_id)

    async def update_prediction(self, prediction_id, **values):
        prediction = self.predictions[prediction_id]
        for key, value in values.items():
            setattr(prediction, key, value)
        return prediction


class FakePublisher:
    def __init__(self) -> None:
        self.completed: list[object] = []

    async def comparison_completed(self, report_id, workspace_id, compatible):
        self.completed.append((report_id, workspace_id, compatible))


def _run(workspace_id, twin_ids, metrics) -> SimulationRun:
    run = SimulationRun(
        workspace_id=workspace_id,
        name="scenario",
        digital_twin_ids=[str(item) for item in twin_ids],
        scenario_config={},
        status="completed",
        results={"execution_metrics": metrics},
        initiated_by=uuid4(),
    )
    run.id = uuid4()
    run.created_at = datetime.now(UTC)
    return run


def _report(primary_id, secondary_id=None, prediction_id=None) -> SimulationComparisonReport:
    report = SimulationComparisonReport(
        comparison_type="prediction_vs_actual" if prediction_id else "simulation_vs_simulation",
        primary_run_id=primary_id,
        secondary_run_id=secondary_id,
        prediction_id=prediction_id,
        metric_differences=[],
        status="pending",
        compatible=True,
        incompatibility_reasons=[],
    )
    report.id = uuid4()
    report.created_at = datetime.now(UTC)
    return report


@pytest.mark.asyncio
async def test_analyze_computes_metric_differences_and_verdict() -> None:
    workspace_id = uuid4()
    twin_id = uuid4()
    repository = FakeRepository()
    primary = _run(
        workspace_id,
        [twin_id],
        {
            "quality_score": [0.9, 0.92, 0.94],
            "error_rate": [0.01, 0.01, 0.02],
        },
    )
    secondary = _run(
        workspace_id,
        [twin_id],
        {
            "quality_score": [0.5, 0.52, 0.54],
            "error_rate": [0.1, 0.12, 0.11],
        },
    )
    report = _report(primary.id, secondary.id)
    repository.runs = {primary.id: primary, secondary.id: secondary}
    repository.reports = {report.id: report}
    publisher = FakePublisher()
    analyzer = ComparisonAnalyzer(
        repository=repository,
        clickhouse_client=None,
        publisher=publisher,
        settings=PlatformSettings(),
    )

    updated = await analyzer.analyze(report=report, workspace_id=workspace_id)

    assert updated.status == "completed"
    assert updated.compatible is True
    assert {item["metric"] for item in updated.metric_differences} == {
        "quality_score",
        "error_rate",
    }
    assert updated.overall_verdict in {"primary_better", "equivalent"}
    assert publisher.completed == [(report.id, workspace_id, True)]


@pytest.mark.asyncio
async def test_incompatible_comparison_records_reasons_and_raises_422() -> None:
    workspace_id = uuid4()
    repository = FakeRepository()
    primary = _run(workspace_id, [uuid4()], {"quality_score": [1.0]})
    secondary = _run(workspace_id, [uuid4()], {"quality_score": [1.0]})
    report = _report(primary.id, secondary.id)
    repository.runs = {primary.id: primary, secondary.id: secondary}
    repository.reports = {report.id: report}
    analyzer = ComparisonAnalyzer(
        repository=repository,
        clickhouse_client=None,
        publisher=FakePublisher(),
        settings=PlatformSettings(),
    )

    with pytest.raises(IncompatibleComparisonError) as exc_info:
        await analyzer.analyze(report=report, workspace_id=workspace_id)

    assert exc_info.value.status_code == 422
    assert report.compatible is False
    assert report.incompatibility_reasons == ["digital_twin_ids do not match"]


@pytest.mark.asyncio
async def test_prediction_vs_actual_updates_accuracy_report() -> None:
    workspace_id = uuid4()
    repository = FakeRepository()
    primary = _run(workspace_id, [uuid4()], {"quality_score": [0.9], "error_rate": [0.05]})
    prediction = BehavioralPrediction(
        digital_twin_id=uuid4(),
        condition_modifiers={},
        predicted_metrics={
            "quality_score": {"predicted_value": 0.81},
            "error_rate": {"predicted_value": 0.1},
        },
        history_days_used=30,
        status="completed",
    )
    prediction.id = uuid4()
    prediction.created_at = datetime.now(UTC)
    report = _report(primary.id, prediction_id=prediction.id)
    repository.runs = {primary.id: primary}
    repository.predictions = {prediction.id: prediction}
    repository.reports = {report.id: report}
    analyzer = ComparisonAnalyzer(
        repository=repository,
        clickhouse_client=None,
        publisher=FakePublisher(),
        settings=PlatformSettings(),
    )

    updated = await analyzer.analyze(report=report, workspace_id=workspace_id)

    assert updated.status == "completed"
    assert prediction.accuracy_report["quality_score"]["accuracy_pct"] == pytest.approx(90.0)
    assert prediction.accuracy_report["error_rate"]["accuracy_pct"] == pytest.approx(0.0)
