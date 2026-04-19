from __future__ import annotations

from platform.agentops.adaptation import analyzer as analyzer_module
from platform.agentops.adaptation.analyzer import (
    AdaptationSignal,
    BehavioralAnalyzer,
    _coerce_float,
    _coerce_int,
    _coerce_str,
    _linear_regression_slope,
    _quality_slope,
)
from uuid import uuid4

import pytest


class _ClickHouseStub:
    def __init__(
        self, *, quality_rows, cost_rows, failure_rows, tool_rows, convergence_rows=None
    ) -> None:
        self.quality_rows = quality_rows
        self.cost_rows = cost_rows
        self.failure_rows = failure_rows
        self.tool_rows = tool_rows
        self.convergence_rows = convergence_rows or []

    async def execute_query(self, sql: str, params: dict[str, object] | None = None):
        del params
        normalized = " ".join(sql.split()).lower()
        if "quality_trend_slope" in normalized or "average_quality" in normalized:
            return self.quality_rows
        if "agent_cost_quality_ratio" in normalized:
            return self.cost_rows
        if "failure_rate" in normalized:
            return self.failure_rows
        if "tool_utilization_rate" in normalized:
            return self.tool_rows
        if "average_loops" in normalized or "self_correction_loops" in normalized:
            return self.convergence_rows
        raise AssertionError(f"Unexpected query: {sql}")


@pytest.mark.asyncio
async def test_analyzer_detects_declining_quality_trend() -> None:
    analyzer = BehavioralAnalyzer(
        clickhouse_client=_ClickHouseStub(
            quality_rows=[
                {"day_index": index, "average_quality": score}
                for index, score in enumerate(
                    [0.91, 0.89, 0.88, 0.86, 0.85, 0.83, 0.81, 0.79, 0.77, 0.75, 0.73, 0.71]
                )
            ],
            cost_rows=[{"agent_cost_quality_ratio": 0.8, "workspace_cost_quality_ratio": 0.7}],
            failure_rows=[{"failure_rate": 0.05, "failure_count": 2, "total_count": 40}],
            tool_rows=[{"tool_utilization_rate": 0.42, "tool_invocations": 84, "tool_slots": 200}],
        )
    )

    signals = await analyzer.analyze("finance:agent", uuid4())

    assert [signal.rule_type for signal in signals] == ["quality_trend"]
    assert signals[0].metrics["trend_slope_per_day"] < -0.005


@pytest.mark.asyncio
async def test_analyzer_detects_cost_quality_imbalance() -> None:
    analyzer = BehavioralAnalyzer(
        clickhouse_client=_ClickHouseStub(
            quality_rows=[{"day_index": index, "average_quality": 0.88} for index in range(14)],
            cost_rows=[{"agent_cost_quality_ratio": 2.4, "workspace_cost_quality_ratio": 1.0}],
            failure_rows=[{"failure_rate": 0.03, "failure_count": 1, "total_count": 40}],
            tool_rows=[{"tool_utilization_rate": 0.35, "tool_invocations": 70, "tool_slots": 200}],
        )
    )

    signals = await analyzer.analyze("finance:agent", uuid4())

    signal = next(item for item in signals if item.rule_type == "cost_quality")
    assert signal.metrics["agent_cost_quality_ratio"] == pytest.approx(2.4)
    assert signal.metrics["ratio_vs_workspace_average"] == pytest.approx(2.4)


@pytest.mark.asyncio
async def test_analyzer_detects_failure_pattern_hotspot() -> None:
    analyzer = BehavioralAnalyzer(
        clickhouse_client=_ClickHouseStub(
            quality_rows=[{"day_index": index, "average_quality": 0.9} for index in range(14)],
            cost_rows=[{"agent_cost_quality_ratio": 1.2, "workspace_cost_quality_ratio": 1.0}],
            failure_rows=[
                {
                    "failure_rate": 0.27,
                    "failure_count": 12,
                    "total_count": 44,
                    "top_failure_type": "tool_timeout",
                }
            ],
            tool_rows=[{"tool_utilization_rate": 0.4, "tool_invocations": 80, "tool_slots": 200}],
        )
    )

    signals = await analyzer.analyze("finance:agent", uuid4())

    signal = next(item for item in signals if item.rule_type == "failure_pattern")
    assert signal.metrics["failure_rate"] == pytest.approx(0.27)
    assert signal.metrics["top_failure_type"] == "tool_timeout"


@pytest.mark.asyncio
async def test_analyzer_detects_low_tool_utilization() -> None:
    analyzer = BehavioralAnalyzer(
        clickhouse_client=_ClickHouseStub(
            quality_rows=[{"day_index": index, "average_quality": 0.9} for index in range(14)],
            cost_rows=[{"agent_cost_quality_ratio": 1.0, "workspace_cost_quality_ratio": 1.0}],
            failure_rows=[{"failure_rate": 0.05, "failure_count": 2, "total_count": 40}],
            tool_rows=[{"tool_utilization_rate": 0.08, "tool_invocations": 8, "tool_slots": 100}],
        )
    )

    signals = await analyzer.analyze("finance:agent", uuid4())

    signal = next(item for item in signals if item.rule_type == "tool_utilization")
    assert signal.metrics["tool_utilization_rate"] == pytest.approx(0.08)


@pytest.mark.asyncio
async def test_analyzer_returns_empty_list_when_metrics_are_healthy() -> None:
    analyzer = BehavioralAnalyzer(
        clickhouse_client=_ClickHouseStub(
            quality_rows=[{"day_index": index, "average_quality": 0.9} for index in range(14)],
            cost_rows=[{"agent_cost_quality_ratio": 1.1, "workspace_cost_quality_ratio": 1.0}],
            failure_rows=[{"failure_rate": 0.08, "failure_count": 3, "total_count": 40}],
            tool_rows=[{"tool_utilization_rate": 0.28, "tool_invocations": 28, "tool_slots": 100}],
        )
    )

    signals = await analyzer.analyze("finance:agent", uuid4())

    assert signals == []


@pytest.mark.asyncio
async def test_analyzer_handles_missing_clickhouse_and_sparse_rows() -> None:
    analyzer = BehavioralAnalyzer(clickhouse_client=None)
    workspace_id = uuid4()

    assert await analyzer._fetch_quality_trend("finance:agent", workspace_id) == []
    assert await analyzer._fetch_cost_quality("finance:agent", workspace_id) == {}
    assert await analyzer._fetch_failure_pattern("finance:agent", workspace_id) == {}
    assert await analyzer._fetch_tool_utilization("finance:agent", workspace_id) == {}
    assert await analyzer.analyze("finance:agent", workspace_id) == []


@pytest.mark.asyncio
async def test_analyzer_detects_convergence_regression_and_resets_degradation_state() -> None:
    analyzer = BehavioralAnalyzer(
        clickhouse_client=_ClickHouseStub(
            quality_rows=[{"day_index": index, "average_quality": 0.9} for index in range(14)],
            cost_rows=[{"agent_cost_quality_ratio": 1.0, "workspace_cost_quality_ratio": 1.0}],
            failure_rows=[{"failure_rate": 0.05, "failure_count": 2, "total_count": 40}],
            tool_rows=[{"tool_utilization_rate": 0.25, "tool_invocations": 25, "tool_slots": 100}],
        )
    )

    async def _fetch_convergence(agent_fqn: str, workspace_id):
        del agent_fqn, workspace_id
        return [
            {"average_loops": 2.0},
            {"average_loops": 2.1},
            {"average_loops": 5.2},
            {"average_loops": 5.5},
        ]

    analyzer._fetch_convergence_regression = _fetch_convergence  # type: ignore[method-assign]

    signals = await analyzer.analyze("finance:agent", uuid4())

    convergence = next(item for item in signals if item.rule_type == "convergence_regression")
    assert convergence.metrics["baseline_loops"] == pytest.approx(2.05)
    assert convergence.metrics["recent_loops"] == pytest.approx(5.35)
    assert analyzer.is_degraded is False


def test_analyzer_helper_functions_cover_payload_coercion_and_linear_regression(
    monkeypatch,
) -> None:
    signal = AdaptationSignal(
        rule_type="quality_trend",
        metrics={"score": 1.0},
        rationale="refresh",
    )
    monkeypatch.setattr(analyzer_module, "np", None)

    assert signal.as_payload()["rule_type"] == "quality_trend"
    assert _quality_slope([{"average_quality": "bad"}, {"average_quality": None}]) is None
    assert (
        _quality_slope(
            [{"average_quality": 0.9}, {"average_quality": 0.8}, {"average_quality": 0.7}]
        )
        < 0
    )
    assert _linear_regression_slope([1.0, 1.0, 1.0]) == 0.0
    assert _coerce_float("1.5") == 1.5
    assert _coerce_float(object()) is None
    assert _coerce_int("7") == 7
    assert _coerce_int("bad") == 0
    assert _coerce_str(" demo ") == "demo"
    assert _coerce_str("   ") is None
