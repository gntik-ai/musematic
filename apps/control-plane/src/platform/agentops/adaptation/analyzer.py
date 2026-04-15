from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, cast
from uuid import UUID

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover
    np = None


@dataclass(frozen=True, slots=True)
class AdaptationSignal:
    rule_type: str
    metrics: dict[str, float | int | str | None]
    rationale: str

    def as_payload(self) -> dict[str, object]:
        return asdict(self)


class BehavioralAnalyzer:
    def __init__(self, *, clickhouse_client: Any | None) -> None:
        self.clickhouse_client = clickhouse_client

    async def analyze(self, agent_fqn: str, workspace_id: UUID) -> list[AdaptationSignal]:
        quality_rows = await self._fetch_quality_trend(agent_fqn, workspace_id)
        cost_row = await self._fetch_cost_quality(agent_fqn, workspace_id)
        failure_row = await self._fetch_failure_pattern(agent_fqn, workspace_id)
        tool_row = await self._fetch_tool_utilization(agent_fqn, workspace_id)

        signals: list[AdaptationSignal] = []
        trend_slope = _quality_slope(quality_rows)
        if trend_slope is not None and trend_slope < -0.005:
            latest_quality = (
                _coerce_float(quality_rows[-1].get("average_quality"))
                if quality_rows
                else None
            )
            signals.append(
                AdaptationSignal(
                    rule_type="quality_trend",
                    metrics={
                        "trend_slope_per_day": trend_slope,
                        "latest_quality": latest_quality,
                        "window_days": len(quality_rows),
                    },
                    rationale=(
                        "Quality has been trending down faster than -0.5 percentage points per day "
                        "over the last 14 days."
                    ),
                )
            )

        agent_ratio = _coerce_float(cost_row.get("agent_cost_quality_ratio"))
        workspace_ratio = _coerce_float(cost_row.get("workspace_cost_quality_ratio"))
        if (
            agent_ratio is not None
            and workspace_ratio is not None
            and workspace_ratio > 0.0
            and agent_ratio > workspace_ratio * 2.0
        ):
            ratio_vs_workspace = agent_ratio / workspace_ratio
            signals.append(
                AdaptationSignal(
                    rule_type="cost_quality",
                    metrics={
                        "agent_cost_quality_ratio": agent_ratio,
                        "workspace_cost_quality_ratio": workspace_ratio,
                        "ratio_vs_workspace_average": ratio_vs_workspace,
                    },
                    rationale=(
                        "The agent is spending more than 2x the workspace average cost per "
                        "quality point, "
                        "which suggests model parameter tuning."
                    ),
                )
            )

        failure_rate = _coerce_float(failure_row.get("failure_rate"))
        if failure_rate is not None and failure_rate > 0.20:
            signals.append(
                AdaptationSignal(
                    rule_type="failure_pattern",
                    metrics={
                        "failure_rate": failure_rate,
                        "failure_count": _coerce_int(failure_row.get("failure_count")),
                        "total_count": _coerce_int(failure_row.get("total_count")),
                        "top_failure_type": _coerce_str(failure_row.get("top_failure_type")),
                    },
                    rationale=(
                        "More than 20% of recent executions are failing with a recurring pattern, "
                        "which suggests updating the approach text and recovery logic."
                    ),
                )
            )

        tool_utilization = _coerce_float(tool_row.get("tool_utilization_rate"))
        if tool_utilization is not None and tool_utilization < 0.10:
            signals.append(
                AdaptationSignal(
                    rule_type="tool_utilization",
                    metrics={
                        "tool_utilization_rate": tool_utilization,
                        "tool_invocations": _coerce_int(tool_row.get("tool_invocations")),
                        "tool_slots": _coerce_int(tool_row.get("tool_slots")),
                    },
                    rationale=(
                        "Tool utilization is below 10%, which suggests simplifying or "
                        "re-prioritizing "
                        "the tool selection strategy."
                    ),
                )
            )
        return signals

    async def _fetch_quality_trend(
        self,
        agent_fqn: str,
        workspace_id: UUID,
    ) -> list[dict[str, Any]]:
        if self.clickhouse_client is None:
            return []
        return cast(
            list[dict[str, Any]],
            await self.clickhouse_client.execute_query(
                """
                SELECT
                    rowNumberInAllBlocks() - 1 AS day_index,
                    avg(quality_score) AS average_quality
                FROM agentops_behavioral_versions
                WHERE workspace_id = {workspace_id:UUID}
                  AND agent_fqn = %(agent_fqn)s
                  AND measured_at >= now() - INTERVAL 14 DAY
                  AND quality_score IS NOT NULL
                GROUP BY toDate(measured_at)
                ORDER BY toDate(measured_at) ASC
                """,
                {"workspace_id": workspace_id, "agent_fqn": agent_fqn},
            ),
        )

    async def _fetch_cost_quality(self, agent_fqn: str, workspace_id: UUID) -> dict[str, Any]:
        if self.clickhouse_client is None:
            return {}
        rows = await self.clickhouse_client.execute_query(
            """
            WITH workspace_average AS (
                SELECT
                    avg(cost_usd / greatest(quality_score, 0.0001))
                    AS workspace_cost_quality_ratio
                FROM agentops_behavioral_versions
                WHERE workspace_id = {workspace_id:UUID}
                  AND measured_at >= now() - INTERVAL 14 DAY
                  AND quality_score IS NOT NULL
                  AND cost_usd IS NOT NULL
            )
            SELECT
                avg(cost_usd / greatest(quality_score, 0.0001)) AS agent_cost_quality_ratio,
                any(workspace_average.workspace_cost_quality_ratio) AS workspace_cost_quality_ratio
            FROM agentops_behavioral_versions
            CROSS JOIN workspace_average
            WHERE workspace_id = {workspace_id:UUID}
              AND agent_fqn = %(agent_fqn)s
              AND measured_at >= now() - INTERVAL 14 DAY
              AND quality_score IS NOT NULL
              AND cost_usd IS NOT NULL
            """,
            {"workspace_id": workspace_id, "agent_fqn": agent_fqn},
        )
        return rows[0] if rows else {}

    async def _fetch_failure_pattern(self, agent_fqn: str, workspace_id: UUID) -> dict[str, Any]:
        if self.clickhouse_client is None:
            return {}
        rows = await self.clickhouse_client.execute_query(
            """
            SELECT
                count() AS total_count,
                countIf(
                    failure_event_type IS NOT NULL AND failure_event_type != ''
                ) AS failure_count,
                countIf(
                    failure_event_type IS NOT NULL AND failure_event_type != ''
                ) / greatest(count(), 1) AS failure_rate,
                anyHeavy(failure_event_type) AS top_failure_type
            FROM agentops_behavioral_versions
            WHERE workspace_id = {workspace_id:UUID}
              AND agent_fqn = %(agent_fqn)s
              AND measured_at >= now() - INTERVAL 7 DAY
            """,
            {"workspace_id": workspace_id, "agent_fqn": agent_fqn},
        )
        return rows[0] if rows else {}

    async def _fetch_tool_utilization(self, agent_fqn: str, workspace_id: UUID) -> dict[str, Any]:
        if self.clickhouse_client is None:
            return {}
        rows = await self.clickhouse_client.execute_query(
            """
            SELECT
                sum(toUInt64OrZero(tool_invocation_count)) AS tool_invocations,
                sum(greatest(toUInt64OrZero(available_tool_count), 1)) AS tool_slots,
                sum(toUInt64OrZero(tool_invocation_count))
                    / greatest(
                        sum(greatest(toUInt64OrZero(available_tool_count), 1)),
                        1
                    ) AS tool_utilization_rate
            FROM agentops_behavioral_versions
            WHERE workspace_id = {workspace_id:UUID}
              AND agent_fqn = %(agent_fqn)s
              AND measured_at >= now() - INTERVAL 14 DAY
            """,
            {"workspace_id": workspace_id, "agent_fqn": agent_fqn},
        )
        return rows[0] if rows else {}


def _quality_slope(rows: list[dict[str, Any]]) -> float | None:
    if len(rows) < 2:
        return None
    y_values: list[float] = []
    for row in rows:
        quality = _coerce_float(row.get("average_quality"))
        if quality is not None:
            y_values.append(quality)
    if len(y_values) < 2:
        return None
    if np is not None:
        x_values = np.arange(len(y_values), dtype=float)
        slope, _ = np.polyfit(x_values, np.asarray(y_values, dtype=float), deg=1)
        return float(slope)
    return _linear_regression_slope(y_values)


def _linear_regression_slope(values: list[float]) -> float:
    x_values = list(range(len(values)))
    mean_x = sum(x_values) / len(x_values)
    mean_y = sum(values) / len(values)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, values, strict=False))
    denominator = sum((x - mean_x) ** 2 for x in x_values)
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
