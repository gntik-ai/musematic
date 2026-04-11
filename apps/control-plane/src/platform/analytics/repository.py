from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.analytics.exceptions import AnalyticsStoreUnavailableError
from platform.analytics.models import CostModel
from platform.analytics.schemas import Granularity
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.exceptions import ClickHouseClientError
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

USAGE_EVENT_COLUMNS = [
    "event_id",
    "execution_id",
    "workspace_id",
    "agent_fqn",
    "model_id",
    "provider",
    "timestamp",
    "input_tokens",
    "output_tokens",
    "execution_duration_ms",
    "self_correction_loops",
    "reasoning_tokens",
    "cost_usd",
    "pipeline_version",
    "ingested_at",
]

QUALITY_EVENT_COLUMNS = [
    "event_id",
    "execution_id",
    "workspace_id",
    "agent_fqn",
    "model_id",
    "timestamp",
    "quality_score",
    "eval_suite_id",
    "ingested_at",
]


class CostModelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_pricing(self, model_id: str) -> CostModel | None:
        result = await self.session.execute(
            select(CostModel)
            .where(
                CostModel.model_id == model_id,
                CostModel.is_active.is_(True),
            )
            .order_by(CostModel.valid_from.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[CostModel]:
        result = await self.session.execute(
            select(CostModel).order_by(CostModel.model_id.asc(), CostModel.valid_from.desc())
        )
        return list(result.scalars().all())


class AnalyticsRepository:
    def __init__(self, client: AsyncClickHouseClient) -> None:
        self.client = client

    async def insert_usage_events_batch(self, events: list[dict[str, Any]]) -> None:
        await self._guard_insert("analytics_usage_events", events, USAGE_EVENT_COLUMNS)

    async def insert_quality_events_batch(self, events: list[dict[str, Any]]) -> None:
        await self._guard_insert("analytics_quality_events", events, QUALITY_EVENT_COLUMNS)

    async def query_usage_rollups(
        self,
        workspace_id: UUID,
        granularity: Granularity,
        start_time: datetime,
        end_time: datetime,
        agent_fqn: str | None,
        model_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        view_name, period_column = _rollup_target(granularity)
        filters = [
            "workspace_id = {workspace_id:UUID}",
            f"{period_column} >= {{start_time:DateTime64}}",
            f"{period_column} <= {{end_time:DateTime64}}",
        ]
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "start_time": _utc(start_time),
            "end_time": _utc(end_time),
            "limit": limit,
            "offset": offset,
        }
        if agent_fqn:
            filters.append("agent_fqn = {agent_fqn:String}")
            params["agent_fqn"] = agent_fqn
        if model_id:
            filters.append("model_id = {model_id:String}")
            params["model_id"] = model_id

        where_sql = " AND ".join(filters)
        select_sql = f"""
            SELECT
                {period_column} AS period,
                workspace_id,
                agent_fqn,
                model_id,
                provider,
                countMerge(execution_count_state) AS execution_count,
                sumMerge(input_tokens_state) AS input_tokens,
                sumMerge(output_tokens_state) AS output_tokens,
                sumMerge(input_tokens_state) + sumMerge(output_tokens_state) AS total_tokens,
                toFloat64(sumMerge(cost_usd_state)) AS cost_usd,
                toFloat64(avgMerge(avg_duration_ms_state)) AS avg_duration_ms,
                sumMerge(self_correction_loops_state) AS self_correction_loops
            FROM {view_name}
            WHERE {where_sql}
            GROUP BY period, workspace_id, agent_fqn, model_id, provider
            ORDER BY period ASC, agent_fqn ASC, model_id ASC
            LIMIT {{limit:UInt32}} OFFSET {{offset:UInt32}}
        """
        total_sql = f"""
            SELECT count() AS total
            FROM (
                SELECT 1
                FROM {view_name}
                WHERE {where_sql}
                GROUP BY {period_column}, workspace_id, agent_fqn, model_id, provider
            )
        """
        rows = await self._guard_query(select_sql, params)
        total_rows = await self._guard_query(total_sql, params)
        total = int(total_rows[0]["total"]) if total_rows else 0
        return rows, total

    async def query_cost_quality_join(
        self,
        workspace_id: UUID,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT
                u.agent_fqn,
                u.model_id,
                any(u.provider) AS provider,
                toFloat64(sum(u.cost_usd)) AS total_cost_usd,
                count() AS execution_count,
                avg(q.quality_score) AS avg_quality_score
            FROM analytics_usage_events AS u
            LEFT JOIN analytics_quality_events AS q
                ON u.execution_id = q.execution_id
            WHERE
                u.workspace_id = {workspace_id:UUID}
                AND u.timestamp >= {start_time:DateTime64}
                AND u.timestamp <= {end_time:DateTime64}
            GROUP BY u.agent_fqn, u.model_id
            ORDER BY total_cost_usd ASC, u.agent_fqn ASC, u.model_id ASC
        """
        return await self._guard_query(
            sql,
            {
                "workspace_id": workspace_id,
                "start_time": _utc(start_time),
                "end_time": _utc(end_time),
            },
        )

    async def query_daily_cost_series(
        self,
        workspace_id: UUID,
        days_back: int,
    ) -> list[dict[str, Any]]:
        start_time = datetime.now(UTC) - timedelta(days=days_back)
        sql = """
            SELECT
                day,
                toFloat64(sumMerge(cost_usd_state)) AS cost_usd
            FROM analytics_usage_daily
            WHERE
                workspace_id = {workspace_id:UUID}
                AND day >= {start_time:DateTime64}
            GROUP BY day
            ORDER BY day ASC
        """
        return await self._guard_query(
            sql,
            {
                "workspace_id": workspace_id,
                "start_time": start_time,
            },
        )

    async def query_agent_metrics(self, workspace_id: UUID) -> list[dict[str, Any]]:
        sql = """
            SELECT
                u.agent_fqn,
                u.model_id,
                any(u.provider) AS provider,
                avg(q.quality_score) AS avg_quality_score,
                avg(u.self_correction_loops) AS avg_self_correction_loops,
                avg(u.input_tokens) AS avg_input_tokens,
                avg(u.output_tokens) AS avg_output_tokens,
                count() AS execution_count,
                countIf(u.timestamp >= now() - INTERVAL 30 DAY) AS execution_count_last_30d,
                avg(u.cost_usd) AS avg_cost_per_execution,
                min(u.timestamp) AS first_seen
            FROM analytics_usage_events AS u
            LEFT JOIN analytics_quality_events AS q
                ON u.execution_id = q.execution_id
            WHERE u.workspace_id = {workspace_id:UUID}
            GROUP BY u.agent_fqn, u.model_id
            ORDER BY u.agent_fqn ASC, u.model_id ASC
        """
        return await self._guard_query(sql, {"workspace_id": workspace_id})

    async def query_fleet_baselines(self, workspace_id: UUID) -> dict[str, float]:
        sql = """
            SELECT
                avg(self_correction_loops) AS avg_loops,
                medianOrNull(q.quality_score) AS median_quality,
                quantile(0.95)(
                    toFloat64(input_tokens) / greatest(toFloat64(output_tokens), 1.0)
                ) AS p95_input_output_ratio
            FROM analytics_usage_events AS u
            LEFT JOIN analytics_quality_events AS q
                ON u.execution_id = q.execution_id
            WHERE u.workspace_id = {workspace_id:UUID}
        """
        rows = await self._guard_query(sql, {"workspace_id": workspace_id})
        row = rows[0] if rows else {}
        return {
            "avg_loops": float(row.get("avg_loops") or 0.0),
            "median_quality": float(row.get("median_quality") or 0.0),
            "p95_input_output_ratio": float(row.get("p95_input_output_ratio") or 0.0),
        }

    async def query_kpi_series(
        self,
        workspace_id: UUID,
        granularity: Granularity,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        _, period_column = _rollup_target(granularity)
        period_expr = _quality_period_expr(granularity)
        view_name, _ = _rollup_target(granularity)
        sql = f"""
            WITH usage AS (
                SELECT
                    {period_column} AS period,
                    toFloat64(sumMerge(cost_usd_state)) AS total_cost_usd,
                    countMerge(execution_count_state) AS execution_count,
                    toFloat64(avgMerge(avg_duration_ms_state)) AS avg_duration_ms
                FROM {view_name}
                WHERE
                    workspace_id = {{workspace_id:UUID}}
                    AND {period_column} >= {{start_time:DateTime64}}
                    AND {period_column} <= {{end_time:DateTime64}}
                GROUP BY period
            ),
            quality AS (
                SELECT
                    {period_expr} AS period,
                    avg(quality_score) AS avg_quality_score
                FROM analytics_quality_events
                WHERE
                    workspace_id = {{workspace_id:UUID}}
                    AND timestamp >= {{start_time:DateTime64}}
                    AND timestamp <= {{end_time:DateTime64}}
                GROUP BY period
            )
            SELECT
                usage.period,
                usage.total_cost_usd,
                usage.execution_count,
                usage.avg_duration_ms,
                quality.avg_quality_score AS avg_quality_score,
                if(
                    isNull(quality.avg_quality_score) OR quality.avg_quality_score = 0,
                    NULL,
                    usage.total_cost_usd / quality.avg_quality_score
                ) AS cost_per_quality
            FROM usage
            LEFT JOIN quality USING (period)
            ORDER BY usage.period ASC
        """
        return await self._guard_query(
            sql,
            {
                "workspace_id": workspace_id,
                "start_time": _utc(start_time),
                "end_time": _utc(end_time),
            },
        )

    async def list_workspace_ids(self) -> list[UUID]:
        rows = await self._guard_query(
            "SELECT DISTINCT workspace_id FROM analytics_usage_events ORDER BY workspace_id ASC"
        )
        return [UUID(str(row["workspace_id"])) for row in rows]

    async def _guard_query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return await self.client.execute_query(sql, params=params)
        except ClickHouseClientError as exc:
            raise AnalyticsStoreUnavailableError(str(exc)) from exc

    async def _guard_insert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        column_names: list[str],
    ) -> None:
        try:
            await self.client.insert(table, rows, column_names)
        except ClickHouseClientError as exc:
            raise AnalyticsStoreUnavailableError(str(exc)) from exc


def _rollup_target(granularity: Granularity) -> tuple[str, str]:
    if granularity == Granularity.HOURLY:
        return "analytics_usage_hourly", "hour"
    if granularity == Granularity.MONTHLY:
        return "analytics_usage_monthly", "month"
    return "analytics_usage_daily", "day"


def _quality_period_expr(granularity: Granularity) -> str:
    if granularity == Granularity.HOURLY:
        return "toStartOfHour(timestamp)"
    if granularity == Granularity.MONTHLY:
        return "toStartOfMonth(timestamp)"
    return "toStartOfDay(timestamp)"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
