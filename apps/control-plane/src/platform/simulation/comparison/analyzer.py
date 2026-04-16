from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.simulation.events import SimulationEventPublisher
from platform.simulation.exceptions import IncompatibleComparisonError, SimulationNotFoundError
from platform.simulation.models import SimulationComparisonReport
from platform.simulation.repository import SimulationRepository
from typing import Any
from uuid import UUID


class ComparisonAnalyzer:
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

    async def analyze(
        self,
        *,
        report: SimulationComparisonReport,
        workspace_id: UUID,
    ) -> SimulationComparisonReport:
        if report.comparison_type == "prediction_vs_actual":
            updated = await self._prediction_vs_actual(report, workspace_id)
        else:
            updated = await self._simulation_comparison(report, workspace_id)
        await self.publisher.comparison_completed(updated.id, workspace_id, updated.compatible)
        return updated

    async def _simulation_comparison(
        self,
        report: SimulationComparisonReport,
        workspace_id: UUID,
    ) -> SimulationComparisonReport:
        primary = await self.repository.get_run(report.primary_run_id, workspace_id)
        if primary is None:
            raise SimulationNotFoundError("Simulation run", report.primary_run_id)
        if report.secondary_run_id is None:
            raise IncompatibleComparisonError(["secondary_run_id is required"])
        secondary = await self.repository.get_run(report.secondary_run_id, workspace_id)
        if secondary is None:
            raise SimulationNotFoundError("Simulation run", report.secondary_run_id)
        reasons = _compatibility_reasons(primary.digital_twin_ids, secondary.digital_twin_ids)
        if reasons:
            updated = await self.repository.update_comparison_report(
                report.id,
                status="completed",
                compatible=False,
                incompatibility_reasons=reasons,
                metric_differences=[],
                overall_verdict="inconclusive",
            )
            assert updated is not None
            raise IncompatibleComparisonError(reasons)
        primary_metrics = _metric_series(primary.results or {})
        secondary_metrics = _metric_series(secondary.results or {})
        differences = _metric_differences(
            primary_metrics,
            secondary_metrics,
            self.settings.simulation.comparison_significance_alpha,
        )
        verdict = _overall_verdict(differences)
        updated = await self.repository.update_comparison_report(
            report.id,
            status="completed",
            compatible=True,
            incompatibility_reasons=[],
            metric_differences=differences,
            overall_verdict=verdict,
        )
        assert updated is not None
        return updated

    async def _prediction_vs_actual(
        self,
        report: SimulationComparisonReport,
        workspace_id: UUID,
    ) -> SimulationComparisonReport:
        primary = await self.repository.get_run(report.primary_run_id, workspace_id)
        if primary is None:
            raise SimulationNotFoundError("Simulation run", report.primary_run_id)
        if report.prediction_id is None:
            raise IncompatibleComparisonError(["prediction_id is required"])
        prediction = await self.repository.get_prediction(report.prediction_id, workspace_id)
        if prediction is None:
            raise SimulationNotFoundError("Behavioral prediction", report.prediction_id)
        actual = _actual_metric_values(primary.results or {})
        predicted = _predicted_values(prediction.predicted_metrics or {})
        accuracy_report = _accuracy_report(predicted, actual)
        await self.repository.update_prediction(
            prediction.id,
            accuracy_report=accuracy_report,
        )
        updated = await self.repository.update_comparison_report(
            report.id,
            status="completed",
            compatible=True,
            incompatibility_reasons=[],
            metric_differences=list(accuracy_report.values()),
            overall_verdict="inconclusive",
        )
        assert updated is not None
        return updated


def _compatibility_reasons(primary_ids: list[str], secondary_ids: list[str]) -> list[str]:
    if set(map(str, primary_ids)) == set(map(str, secondary_ids)):
        return []
    return ["digital_twin_ids do not match"]


def _metric_series(results: dict[str, Any]) -> dict[str, list[float]]:
    raw = results.get("execution_metrics", results.get("metrics", {}))
    series: dict[str, list[float]] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, list):
                series[key] = [float(item) for item in value]
            elif isinstance(value, int | float):
                series[key] = [float(value)]
    elif isinstance(raw, list):
        for row in raw:
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                if isinstance(value, int | float):
                    series.setdefault(key, []).append(float(value))
    return series


def _metric_differences(
    primary_metrics: dict[str, list[float]],
    secondary_metrics: dict[str, list[float]],
    alpha: float,
) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    for metric in sorted(set(primary_metrics) & set(secondary_metrics)):
        primary_values = primary_metrics[metric]
        secondary_values = secondary_metrics[metric]
        primary_mean = _mean(primary_values)
        secondary_mean = _mean(secondary_values)
        delta = primary_mean - secondary_mean
        p_value = _ttest_pvalue(primary_values, secondary_values)
        differences.append(
            {
                "metric": metric,
                "primary_mean": primary_mean,
                "secondary_mean": secondary_mean,
                "delta": delta,
                "direction": _direction(metric, delta),
                "p_value": p_value,
                "significance": _significance(p_value, alpha),
            }
        )
    return differences


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _ttest_pvalue(primary_values: list[float], secondary_values: list[float]) -> float:
    try:
        from scipy import stats

        result = stats.ttest_ind(primary_values, secondary_values, equal_var=False)
        return float(result.pvalue)
    except Exception:
        return 1.0 if abs(_mean(primary_values) - _mean(secondary_values)) < 1e-9 else 0.01


def _direction(metric: str, delta: float) -> str:
    if abs(delta) < 1e-9:
        return "neutral"
    lower_is_better = any(token in metric for token in ("error", "latency", "response_time"))
    better = delta < 0 if lower_is_better else delta > 0
    return "better" if better else "worse"


def _significance(p_value: float, alpha: float) -> str:
    if p_value < min(alpha, 0.01):
        return "high"
    if p_value < alpha:
        return "medium"
    return "low"


def _overall_verdict(differences: list[dict[str, Any]]) -> str:
    meaningful = [item for item in differences if item["significance"] != "low"]
    if not meaningful:
        return "equivalent"
    better = sum(1 for item in meaningful if item["direction"] == "better")
    worse = sum(1 for item in meaningful if item["direction"] == "worse")
    if better > worse:
        return "primary_better"
    if worse > better:
        return "secondary_better"
    return "equivalent"


def _predicted_values(metrics: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, dict) and "predicted_value" in value:
            values[key] = float(value["predicted_value"])
        elif isinstance(value, int | float):
            values[key] = float(value)
    return values


def _actual_metric_values(results: dict[str, Any]) -> dict[str, float]:
    return {key: _mean(value) for key, value in _metric_series(results).items()}


def _accuracy_report(
    predicted: dict[str, float],
    actual: dict[str, float],
) -> dict[str, dict[str, float | str]]:
    report: dict[str, dict[str, float | str]] = {}
    for metric, predicted_value in predicted.items():
        actual_value = actual.get(metric)
        if actual_value is None or actual_value == 0.0:
            accuracy_pct = 0.0
        else:
            accuracy_pct = 100 - abs((predicted_value - actual_value) / actual_value * 100)
        report[metric] = {
            "metric": metric,
            "predicted": predicted_value,
            "actual": actual_value if actual_value is not None else 0.0,
            "accuracy_pct": max(0.0, accuracy_pct),
        }
    return report
