from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.simulation.models import BehavioralPrediction, DigitalTwin
from platform.simulation.prediction.forecaster import BehavioralForecaster, PredictionWorker
from uuid import uuid4

import pytest


class FakeRepository:
    def __init__(self, twin: DigitalTwin) -> None:
        self.twin = twin
        self.predictions: dict[object, BehavioralPrediction] = {}

    async def get_twin(self, twin_id, workspace_id):
        if twin_id == self.twin.id and workspace_id == self.twin.workspace_id:
            return self.twin
        return None

    async def create_prediction(self, prediction: BehavioralPrediction) -> BehavioralPrediction:
        prediction.id = uuid4()
        prediction.created_at = datetime.now(UTC)
        prediction.digital_twin = self.twin
        self.predictions[prediction.id] = prediction
        return prediction

    async def get_prediction(self, prediction_id, workspace_id=None):
        return self.predictions.get(prediction_id)

    async def update_prediction(self, prediction_id, **values):
        prediction = self.predictions[prediction_id]
        for key, value in values.items():
            setattr(prediction, key, value)
        return prediction

    async def list_pending_predictions(self, limit=50):
        return [item for item in self.predictions.values() if item.status == "pending"][:limit]


class FakeClickHouse:
    def __init__(self, rows):
        self.rows = rows

    async def execute_query(self, sql, params):
        return self.rows


class BrokenClickHouse:
    async def execute_query(self, sql, params):
        raise RuntimeError("clickhouse down")


class FakePublisher:
    def __init__(self) -> None:
        self.completed: list[object] = []

    async def prediction_completed(self, prediction_id, workspace_id, status):
        self.completed.append((prediction_id, workspace_id, status))


def _twin() -> DigitalTwin:
    twin = DigitalTwin(
        workspace_id=uuid4(),
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


def _rows(count: int = 30) -> list[dict[str, float | str | int]]:
    return [
        {
            "date": f"2026-01-{day:02d}",
            "avg_quality_score": 0.6 + day * 0.02,
            "avg_response_time_ms": 100 + day,
            "avg_error_rate": 0.01 + day * 0.001,
            "execution_count": 10,
        }
        for day in range(1, count + 1)
    ]


@pytest.mark.asyncio
async def test_forecast_computes_regression_metrics_and_load_factor() -> None:
    twin = _twin()
    repository = FakeRepository(twin)
    publisher = FakePublisher()
    forecaster = BehavioralForecaster(
        repository=repository,
        clickhouse_client=FakeClickHouse(_rows()),
        publisher=publisher,
        settings=PlatformSettings(),
    )

    prediction = await forecaster.forecast(
        twin_id=twin.id,
        workspace_id=twin.workspace_id,
        condition_modifiers={"load_factor": 2.0},
    )

    assert prediction.status == "completed"
    assert prediction.confidence_level == "high"
    assert prediction.predicted_metrics["quality_score"]["trend"] == "improving"
    assert prediction.predicted_metrics["response_time_ms"]["trend"] == "degrading"
    assert prediction.predicted_metrics["response_time_ms"]["predicted_value"] > 200
    assert publisher.completed == [(prediction.id, twin.workspace_id, "completed")]


@pytest.mark.asyncio
async def test_forecast_marks_insufficient_data_when_history_is_short() -> None:
    twin = _twin()
    repository = FakeRepository(twin)
    forecaster = BehavioralForecaster(
        repository=repository,
        clickhouse_client=FakeClickHouse(_rows(3)),
        publisher=FakePublisher(),
        settings=PlatformSettings(),
    )

    prediction = await forecaster.forecast(twin_id=twin.id, workspace_id=twin.workspace_id)

    assert prediction.status == "insufficient_data"
    assert prediction.confidence_level == "insufficient_data"
    assert prediction.history_days_used == 3


@pytest.mark.asyncio
async def test_prediction_worker_processes_pending_predictions() -> None:
    twin = _twin()
    repository = FakeRepository(twin)
    prediction = await repository.create_prediction(
        BehavioralPrediction(
            digital_twin_id=twin.id,
            condition_modifiers={},
            status="pending",
        )
    )
    forecaster = BehavioralForecaster(
        repository=repository,
        clickhouse_client=FakeClickHouse(_rows()),
        publisher=FakePublisher(),
        settings=PlatformSettings(),
    )

    processed = await PredictionWorker(forecaster, repository).run_once()

    assert processed == 1
    assert prediction.status == "completed"


@pytest.mark.asyncio
async def test_clickhouse_failure_marks_prediction_failed() -> None:
    twin = _twin()
    repository = FakeRepository(twin)
    forecaster = BehavioralForecaster(
        repository=repository,
        clickhouse_client=BrokenClickHouse(),
        publisher=FakePublisher(),
        settings=PlatformSettings(),
    )

    prediction = await forecaster.forecast(twin_id=twin.id, workspace_id=twin.workspace_id)

    assert prediction.status == "failed"
    assert "clickhouse down" in prediction.predicted_metrics["error"]
