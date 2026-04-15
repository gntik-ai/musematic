from __future__ import annotations

import json
from dataclasses import dataclass
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.redis import AsyncRedisClient
from typing import Any, Protocol, cast
from uuid import UUID


@dataclass(slots=True)
class DimensionResult:
    score: float | None
    sample_count: int


class _TrustHealthInterface(Protocol):
    async def get_guardrail_pass_rate(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
    ) -> Any: ...


class _EvalHealthInterface(Protocol):
    async def get_human_grade_aggregate(
        self,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
    ) -> Any: ...


class HealthDimensionProvider:
    def __init__(
        self,
        *,
        redis_client: AsyncRedisClient | Any | None,
        clickhouse_client: AsyncClickHouseClient | Any | None,
        trust_service: _TrustHealthInterface | Any | None,
        eval_suite_service: _EvalHealthInterface | Any | None,
    ) -> None:
        self.redis_client = redis_client
        self.clickhouse_client = clickhouse_client
        self.trust_service = trust_service
        self.eval_suite_service = eval_suite_service

    async def uptime_score(
        self,
        *,
        agent_fqn: str,
        minimum_sample_size: int,
    ) -> DimensionResult:
        client = await self._get_redis_client()
        if client is None:
            return DimensionResult(None, 0)

        raw_scores: list[float] = []
        cursor: int | str = 0
        pattern = f"fleet:member:avail:*:{agent_fqn}"

        while True:
            cursor, keys = await cast(Any, client.scan(cursor=cursor, match=pattern, count=100))
            for key in keys:
                value = await cast(Any, client.get(key))
                score = _parse_availability_score(value)
                if score is not None:
                    raw_scores.append(score)
            if int(cursor) == 0:
                break

        sample_count = len(raw_scores)
        if sample_count < minimum_sample_size or sample_count == 0:
            return DimensionResult(None, sample_count)
        return DimensionResult(round(sum(raw_scores) / sample_count, 2), sample_count)

    async def quality_score(
        self,
        *,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
        minimum_sample_size: int,
    ) -> DimensionResult:
        if self.clickhouse_client is None:
            return DimensionResult(None, 0)
        rows = await self.clickhouse_client.execute_query(
            """
            SELECT
                avg(quality_score) AS average_quality,
                count() AS sample_count
            FROM agentops_behavioral_versions
            WHERE workspace_id = {workspace_id:UUID}
              AND agent_fqn = %(agent_fqn)s
              AND created_at >= now() - INTERVAL %(window_days)s DAY
            """,
            {"workspace_id": workspace_id, "agent_fqn": agent_fqn, "window_days": window_days},
        )
        row = rows[0] if rows else {}
        sample_count = _coerce_int(row.get("sample_count"))
        average_quality = _normalize_score(row.get("average_quality"), scale="ratio")
        if average_quality is None or sample_count < minimum_sample_size:
            return DimensionResult(None, sample_count)
        return DimensionResult(average_quality, sample_count)

    async def safety_score(
        self,
        *,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
        minimum_sample_size: int,
    ) -> DimensionResult:
        if self.trust_service is None:
            return DimensionResult(None, 0)
        response = await self.trust_service.get_guardrail_pass_rate(
            agent_fqn,
            workspace_id,
            window_days,
        )
        score, sample_count = _extract_score_and_samples(
            response,
            value_keys=("pass_rate", "score", "value"),
            scale="ratio",
        )
        if score is not None and sample_count == 0:
            sample_count = minimum_sample_size
        if score is None or sample_count < minimum_sample_size:
            return DimensionResult(None, sample_count)
        return DimensionResult(score, sample_count)

    async def cost_efficiency_score(
        self,
        *,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
        minimum_sample_size: int,
    ) -> DimensionResult:
        if self.clickhouse_client is None:
            return DimensionResult(None, 0)
        rows = await self.clickhouse_client.execute_query(
            """
            WITH workspace_average AS (
                SELECT avg(cost_per_quality_ratio) AS workspace_cost_per_quality
                FROM analytics_cost_models
                WHERE workspace_id = {workspace_id:UUID}
                  AND created_at >= now() - INTERVAL %(window_days)s DAY
            )
            SELECT
                avg(cost_per_quality_ratio) AS cost_per_quality,
                any(workspace_average.workspace_cost_per_quality) AS workspace_cost_per_quality,
                count() AS sample_count
            FROM analytics_cost_models
            CROSS JOIN workspace_average
            WHERE workspace_id = {workspace_id:UUID}
              AND agent_fqn = %(agent_fqn)s
              AND created_at >= now() - INTERVAL %(window_days)s DAY
            """,
            {"workspace_id": workspace_id, "agent_fqn": agent_fqn, "window_days": window_days},
        )
        row = rows[0] if rows else {}
        sample_count = _coerce_int(row.get("sample_count"))
        agent_ratio = _coerce_float(row.get("cost_per_quality"))
        workspace_ratio = _coerce_float(row.get("workspace_cost_per_quality"))
        if (
            sample_count < minimum_sample_size
            or agent_ratio is None
            or workspace_ratio is None
            or agent_ratio <= 0
            or workspace_ratio <= 0
        ):
            return DimensionResult(None, sample_count)

        efficiency = min(workspace_ratio / agent_ratio, 1.0)
        return DimensionResult(round(efficiency * 100.0, 2), sample_count)

    async def satisfaction_score(
        self,
        *,
        agent_fqn: str,
        workspace_id: UUID,
        window_days: int,
        minimum_sample_size: int,
    ) -> DimensionResult:
        if self.eval_suite_service is None:
            return DimensionResult(None, 0)
        method = getattr(self.eval_suite_service, "get_human_grade_aggregate", None)
        if not callable(method):
            return DimensionResult(None, 0)
        response = await cast(Any, method(agent_fqn, workspace_id, window_days))
        score, sample_count = _extract_score_and_samples(
            response,
            value_keys=("aggregate_grade", "average_grade", "score", "value"),
            scale="stars",
        )
        if score is not None and sample_count == 0:
            sample_count = minimum_sample_size
        if score is None or sample_count < minimum_sample_size:
            return DimensionResult(None, sample_count)
        return DimensionResult(score, sample_count)

    async def _get_redis_client(self) -> Any | None:
        if self.redis_client is None:
            return None
        getter = getattr(self.redis_client, "_get_client", None)
        if callable(getter):
            return await cast(Any, getter())
        return getattr(self.redis_client, "client", None)


def _parse_availability_score(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = stripped
        else:
            parsed = stripped
    else:
        parsed = value

    if isinstance(parsed, dict):
        for key in ("uptime_ratio", "availability_ratio", "ratio", "score", "value"):
            if key in parsed:
                return _normalize_score(parsed[key], scale="ratio")
        return None
    return _normalize_score(parsed, scale="ratio")


def _extract_score_and_samples(
    value: Any,
    *,
    value_keys: tuple[str, ...],
    scale: str,
) -> tuple[float | None, int]:
    sample_count = 0
    raw_value: Any | None = None

    if value is None:
        return None, 0
    if isinstance(value, (tuple, list)):
        if value:
            raw_value = value[0]
        if len(value) > 1:
            sample_count = _coerce_int(value[1])
    elif isinstance(value, dict):
        for key in value_keys:
            if key in value:
                raw_value = value[key]
                break
        for key in ("sample_count", "samples", "count"):
            if key in value:
                sample_count = _coerce_int(value[key])
                break
    elif hasattr(value, "__dict__"):
        for key in value_keys:
            if hasattr(value, key):
                raw_value = getattr(value, key)
                break
        for key in ("sample_count", "samples", "count"):
            if hasattr(value, key):
                sample_count = _coerce_int(getattr(value, key))
                break
    else:
        raw_value = value

    return _normalize_score(raw_value, scale=scale), sample_count


def _normalize_score(value: Any, *, scale: str) -> float | None:
    numeric = _coerce_float(value)
    if numeric is None:
        return None
    if scale == "ratio":
        if 0.0 <= numeric <= 1.0:
            return round(numeric * 100.0, 2)
        return round(max(0.0, min(numeric, 100.0)), 2)
    if scale == "stars":
        if 0.0 <= numeric <= 1.0:
            return round(numeric * 100.0, 2)
        if 0.0 <= numeric <= 5.0:
            return round((numeric / 5.0) * 100.0, 2)
        return round(max(0.0, min(numeric, 100.0)), 2)
    return round(max(0.0, min(numeric, 100.0)), 2)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
