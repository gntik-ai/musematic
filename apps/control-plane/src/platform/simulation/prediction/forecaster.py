from __future__ import annotations

import math
from platform.common.config import PlatformSettings
from platform.simulation.events import SimulationEventPublisher
from platform.simulation.exceptions import SimulationNotFoundError
from platform.simulation.models import BehavioralPrediction
from platform.simulation.repository import SimulationRepository
from typing import Any, cast
from uuid import UUID


class BehavioralForecaster:
    def __init__(
        self,
        *,
        repository: SimulationRepository,
        clickhouse_client: Any | None,
        publisher: SimulationEventPublisher,
        settings: PlatformSettings,
    ) -> None:
        self.repository = repository
        self.clickhouse_client = clickhouse_client
        self.publisher = publisher
        self.settings = settings

    async def forecast(
        self,
        *,
        twin_id: UUID,
        workspace_id: UUID,
        condition_modifiers: dict[str, Any] | None = None,
        prediction_id: UUID | None = None,
    ) -> BehavioralPrediction:
        twin = await self.repository.get_twin(twin_id, workspace_id)
        if twin is None:
            raise SimulationNotFoundError("Digital twin", twin_id)
        prediction = (
            await self.repository.get_prediction(prediction_id, workspace_id)
            if prediction_id is not None
            else None
        )
        if prediction is None:
            prediction = await self.repository.create_prediction(
                BehavioralPrediction(
                    digital_twin_id=twin_id,
                    condition_modifiers=condition_modifiers or {},
                    status="pending",
                )
            )
        try:
            rows = await self._load_history(twin.source_agent_fqn, workspace_id)
        except Exception as exc:
            updated = await self.repository.update_prediction(
                prediction.id,
                status="failed",
                confidence_level=None,
                history_days_used=0,
                predicted_metrics={"error": str(exc)},
            )
            assert updated is not None
            await self.publisher.prediction_completed(updated.id, workspace_id, updated.status)
            return updated
        min_days = self.settings.simulation.min_prediction_history_days
        if len(rows) < min_days:
            updated = await self.repository.update_prediction(
                prediction.id,
                status="insufficient_data",
                confidence_level="insufficient_data",
                history_days_used=len(rows),
                predicted_metrics=None,
            )
            assert updated is not None
            await self.publisher.prediction_completed(updated.id, workspace_id, updated.status)
            return updated
        try:
            metrics = _forecast_metrics(rows, condition_modifiers or {})
            confidence = _confidence_level(
                [
                    float(value["r_squared"])
                    for value in metrics.values()
                    if isinstance(value, dict) and "r_squared" in value
                ]
            )
            updated = await self.repository.update_prediction(
                prediction.id,
                status="completed",
                confidence_level=confidence,
                history_days_used=len(rows),
                predicted_metrics=metrics,
            )
        except Exception as exc:
            updated = await self.repository.update_prediction(
                prediction.id,
                status="failed",
                confidence_level=None,
                history_days_used=len(rows),
                predicted_metrics={"error": str(exc)},
            )
        assert updated is not None
        await self.publisher.prediction_completed(updated.id, workspace_id, updated.status)
        return updated

    async def forecast_prediction(self, prediction_id: UUID) -> BehavioralPrediction:
        prediction = await self.repository.get_prediction(prediction_id)
        if prediction is None:
            raise SimulationNotFoundError("Behavioral prediction", prediction_id)
        twin = await self.repository.get_twin(
            prediction.digital_twin_id,
            prediction.digital_twin.workspace_id,
        )
        if twin is None:
            raise SimulationNotFoundError("Digital twin", prediction.digital_twin_id)
        return await self.forecast(
            twin_id=twin.id,
            workspace_id=twin.workspace_id,
            condition_modifiers=prediction.condition_modifiers,
            prediction_id=prediction.id,
        )

    async def _load_history(self, agent_fqn: str, workspace_id: UUID) -> list[dict[str, Any]]:
        if self.clickhouse_client is None:
            return []
        query = """
            SELECT date, avg_quality_score, avg_response_time_ms, avg_error_rate,
                   execution_count
            FROM execution_metrics_daily
            WHERE workspace_id = {workspace_id:String}
              AND agent_fqn = {agent_fqn:String}
              AND date >= today() - {days:UInt16}
            ORDER BY date ASC
        """
        return cast(
            list[dict[str, Any]],
            await self.clickhouse_client.execute_query(
                query,
                {
                    "workspace_id": str(workspace_id),
                    "agent_fqn": agent_fqn,
                    "days": self.settings.simulation.behavioral_history_days,
                },
            ),
        )


class PredictionWorker:
    def __init__(self, forecaster: BehavioralForecaster, repository: SimulationRepository) -> None:
        self.forecaster = forecaster
        self.repository = repository

    async def run_once(self, *, limit: int = 50) -> int:
        predictions = await self.repository.list_pending_predictions(limit=limit)
        processed = 0
        for prediction in predictions:
            await self.forecaster.forecast_prediction(prediction.id)
            processed += 1
        return processed


def _forecast_metrics(
    rows: list[dict[str, Any]],
    condition_modifiers: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    load_factor = float(condition_modifiers.get("load_factor", 1.0))
    metric_specs = {
        "quality_score": ("avg_quality_score", False),
        "response_time_ms": ("avg_response_time_ms", True),
        "error_rate": ("avg_error_rate", True),
    }
    metrics: dict[str, dict[str, Any]] = {}
    for output_name, (row_key, inverse) in metric_specs.items():
        values = [float(row[row_key]) for row in rows if row.get(row_key) is not None]
        regression = _linregress(list(range(len(values))), values)
        next_value = regression["slope"] * len(values) + regression["intercept"]
        if output_name == "response_time_ms":
            next_value *= load_factor
        elif output_name == "error_rate":
            next_value *= load_factor
        elif output_name == "quality_score":
            next_value /= math.sqrt(load_factor)
        residual_std = _residual_std(values, regression["slope"], regression["intercept"])
        ci_delta = 1.96 * residual_std
        metrics[output_name] = {
            "predicted_value": next_value,
            "confidence_interval": [next_value - ci_delta, next_value + ci_delta],
            "trend": _trend_from_slope(regression["slope"], inverse=inverse),
            "slope": regression["slope"],
            "r_squared": regression["r_value"] ** 2,
        }
    return metrics


def _linregress(x_values: list[int], y_values: list[float]) -> dict[str, float]:
    try:
        from scipy import stats

        result = stats.linregress(x_values, y_values)
        return {
            "slope": float(result.slope),
            "intercept": float(result.intercept),
            "r_value": float(result.rvalue),
        }
    except Exception:
        n = len(y_values)
        x_mean = sum(x_values) / n
        y_mean = sum(y_values) / n
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        slope = (
            sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values, strict=False))
            / denominator
            if denominator
            else 0.0
        )
        intercept = y_mean - slope * x_mean
        y_denominator = sum((y - y_mean) ** 2 for y in y_values)
        r_value = (
            sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values, strict=False))
            / math.sqrt(denominator * y_denominator)
            if denominator and y_denominator
            else 0.0
        )
        return {"slope": slope, "intercept": intercept, "r_value": r_value}


def _residual_std(values: list[float], slope: float, intercept: float) -> float:
    if len(values) < 2:
        return 0.0
    residuals = [value - (slope * index + intercept) for index, value in enumerate(values)]
    return math.sqrt(sum(item * item for item in residuals) / max(len(residuals) - 1, 1))


def _trend_from_slope(slope: float, *, inverse: bool) -> str:
    normalized = -slope if inverse else slope
    if normalized > 0.01:
        return "improving"
    if normalized < -0.01:
        return "degrading"
    return "stable"


def _confidence_level(r_squared_values: list[float]) -> str:
    if not r_squared_values:
        return "low"
    r_squared = sum(r_squared_values) / len(r_squared_values)
    if r_squared > 0.7:
        return "high"
    if r_squared >= 0.4:
        return "medium"
    return "low"
