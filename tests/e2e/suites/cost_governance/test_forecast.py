from __future__ import annotations


def test_forecast_schema_contract_contains_confidence_interval() -> None:
    forecast = {
        "workspace_id": "workspace",
        "point_estimate": "125.00",
        "lower_bound": "100.00",
        "upper_bound": "150.00",
        "confidence_level": 0.95,
    }

    assert {"point_estimate", "lower_bound", "upper_bound", "confidence_level"} <= set(forecast)
    assert forecast["lower_bound"] <= forecast["point_estimate"] <= forecast["upper_bound"]
