from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from platform.analytics.schemas import ForecastPoint, ResourcePrediction
from statistics import mean, stdev
from uuid import UUID


class ForecastEngine:
    def forecast(
        self,
        daily_costs: list[float],
        horizon_days: int,
        *,
        workspace_id: UUID,
        start_date: date | None = None,
    ) -> ResourcePrediction:
        generated_at = datetime.now(UTC)
        base_date = start_date or generated_at.date()
        data_points_used = len(daily_costs)
        warning = None
        if data_points_used < 7:
            warning = (
                "Insufficient historical data — "
                f"forecast based on {data_points_used} days of data. "
                "Accuracy will improve with more history."
            )

        if not daily_costs:
            daily_costs = [0.0]
        xs = list(range(len(daily_costs)))
        slope, intercept = self._linear_regression([float(item) for item in xs], daily_costs)
        mean_cost = mean(daily_costs) if daily_costs else 0.0
        residuals = [
            actual - (intercept + slope * float(index))
            for index, actual in enumerate(daily_costs)
        ]
        high_volatility = self._volatility_flag(residuals, mean_cost)
        low_delta, high_delta = self._confidence_interval(residuals, horizon_days)

        if abs(slope) < abs(mean_cost) * 0.01:
            trend_direction = "stable"
        elif slope > 0:
            trend_direction = "increasing"
        else:
            trend_direction = "decreasing"

        forecast_points: list[ForecastPoint] = []
        expected_total = 0.0
        low_total = 0.0
        high_total = 0.0
        for day_offset in range(1, horizon_days + 1):
            forecast_x = float(len(daily_costs) - 1 + day_offset)
            expected = max(intercept + slope * forecast_x, 0.0)
            low = max(expected - low_delta, 0.0)
            high = max(expected + high_delta, 0.0)
            expected_total += expected
            low_total += low
            high_total += high
            forecast_points.append(
                ForecastPoint(
                    date=datetime.combine(base_date + timedelta(days=day_offset), time(), UTC),
                    projected_cost_usd_low=round(low, 4),
                    projected_cost_usd_expected=round(expected, 4),
                    projected_cost_usd_high=round(high, 4),
                )
            )

        return ResourcePrediction(
            workspace_id=workspace_id,
            horizon_days=horizon_days,
            generated_at=generated_at,
            trend_direction=trend_direction,
            high_volatility=high_volatility,
            data_points_used=data_points_used,
            warning=warning,
            daily_forecast=forecast_points,
            total_projected_low=round(low_total, 4),
            total_projected_expected=round(expected_total, 4),
            total_projected_high=round(high_total, 4),
        )

    def _linear_regression(self, xs: list[float], ys: list[float]) -> tuple[float, float]:
        if len(xs) != len(ys):
            raise ValueError("xs and ys must have the same length")
        if not xs:
            return 0.0, 0.0
        mean_x = mean(xs)
        mean_y = mean(ys)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator == 0:
            return 0.0, mean_y
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False))
        slope = numerator / denominator
        intercept = mean_y - slope * mean_x
        return slope, intercept

    def _confidence_interval(
        self,
        residuals: list[float],
        n_future: int,
    ) -> tuple[float, float]:
        if len(residuals) < 2:
            return 0.0, 0.0
        residual_std = stdev(residuals)
        t_factor = 2.0
        spread = t_factor * residual_std * (1.0 + (n_future / max(len(residuals), 1)) ** 0.5)
        return spread, spread

    def _volatility_flag(self, residuals: list[float], mean_cost: float) -> bool:
        if len(residuals) < 2 or mean_cost <= 0:
            return False
        return stdev(residuals) / mean_cost > 0.3
