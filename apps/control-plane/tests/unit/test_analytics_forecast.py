from __future__ import annotations

from platform.analytics.forecast import ForecastEngine
from uuid import uuid4

import pytest


def test_forecast_engine_projects_increasing_trend_with_confidence_bounds() -> None:
    engine = ForecastEngine()

    prediction = engine.forecast(
        [10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0],
        7,
        workspace_id=uuid4(),
    )

    assert prediction.trend_direction == "increasing"
    assert prediction.warning is None
    assert len(prediction.daily_forecast) == 7
    first_point = prediction.daily_forecast[0]
    assert first_point.projected_cost_usd_low <= first_point.projected_cost_usd_expected
    assert first_point.projected_cost_usd_expected <= first_point.projected_cost_usd_high


def test_forecast_engine_marks_stable_and_warns_for_short_history() -> None:
    engine = ForecastEngine()

    prediction = engine.forecast([5.0, 5.01, 4.99], 7, workspace_id=uuid4())

    assert prediction.trend_direction == "stable"
    assert prediction.warning is not None
    assert "forecast based on 3 days of data" in prediction.warning


def test_forecast_engine_flags_high_volatility() -> None:
    engine = ForecastEngine()

    prediction = engine.forecast(
        [10.0, 25.0, 9.0, 28.0, 11.0, 30.0, 8.0, 27.0],
        7,
        workspace_id=uuid4(),
    )

    assert prediction.high_volatility is True


def test_forecast_engine_handles_empty_and_decreasing_inputs() -> None:
    engine = ForecastEngine()

    empty_prediction = engine.forecast([], 7, workspace_id=uuid4())
    decreasing_prediction = engine.forecast(
        [30.0, 25.0, 20.0, 15.0, 10.0, 5.0, 1.0],
        7,
        workspace_id=uuid4(),
    )

    assert empty_prediction.data_points_used == 0
    assert empty_prediction.daily_forecast[0].projected_cost_usd_expected == 0.0
    assert decreasing_prediction.trend_direction == "decreasing"


def test_linear_regression_and_confidence_interval_handle_known_inputs() -> None:
    engine = ForecastEngine()

    slope, intercept = engine._linear_regression([0.0, 1.0, 2.0], [2.0, 4.0, 6.0])
    low_delta, high_delta = engine._confidence_interval([1.0, -1.0, 1.0, -1.0], 7)

    assert slope == pytest.approx(2.0)
    assert intercept == pytest.approx(2.0)
    assert low_delta == pytest.approx(high_delta)
    assert low_delta > 0


def test_linear_regression_confidence_and_volatility_edge_cases() -> None:
    engine = ForecastEngine()

    assert engine._linear_regression([], []) == (0.0, 0.0)
    assert engine._linear_regression([1.0, 1.0], [3.0, 3.0]) == (0.0, 3.0)
    assert engine._confidence_interval([1.0], 7) == (0.0, 0.0)
    assert engine._volatility_flag([1.0], 10.0) is False
    assert engine._volatility_flag([1.0, -1.0], 0.0) is False


def test_linear_regression_rejects_mismatched_lengths() -> None:
    engine = ForecastEngine()

    with pytest.raises(ValueError, match="same length"):
        engine._linear_regression([1.0], [1.0, 2.0])
