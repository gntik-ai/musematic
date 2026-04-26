from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.common.clients.clickhouse import AsyncClickHouseClient, BatchBuffer
from platform.common.config import PlatformSettings
from platform.common.exceptions import ClickHouseClientError
from typing import Any
from uuid import UUID

COST_EVENT_COLUMNS = [
    "event_id",
    "attribution_id",
    "execution_id",
    "workspace_id",
    "agent_id",
    "user_id",
    "cost_type",
    "model_cost_cents",
    "compute_cost_cents",
    "storage_cost_cents",
    "overhead_cost_cents",
    "total_cost_cents",
    "currency",
    "occurred_at",
    "ingested_at",
]


class ClickHouseCostRepository:
    def __init__(
        self,
        client: AsyncClickHouseClient,
        settings: PlatformSettings | None = None,
    ) -> None:
        self.client = client
        cost_settings = getattr(settings, "cost_governance", None)
        max_size = int(getattr(cost_settings, "attribution_clickhouse_batch_size", 500))
        interval = float(
            getattr(cost_settings, "attribution_clickhouse_flush_interval_seconds", 5.0)
        )
        self.batch_buffer = BatchBuffer(
            client=client,
            table="cost_events",
            column_names=COST_EVENT_COLUMNS,
            max_size=max_size,
            flush_interval=interval,
        )

    async def insert_cost_events_batch(self, events: list[dict[str, Any]]) -> None:
        await self.client.insert_batch("cost_events", events, COST_EVENT_COLUMNS)

    async def enqueue_cost_event(self, event: dict[str, Any]) -> None:
        await self.batch_buffer.add(event)

    async def start(self) -> None:
        await self.batch_buffer.start()

    async def stop(self) -> None:
        await self.batch_buffer.stop()

    async def query_cost_rollups(
        self,
        workspace_ids: list[UUID],
        group_by: list[str],
        since: datetime,
        until: datetime,
    ) -> list[dict[str, Any]]:
        if not workspace_ids:
            return []
        dimensions = _dimension_selects(group_by)
        select_sql = ", ".join(item[0] for item in dimensions)
        group_sql = ", ".join(item[1] for item in dimensions)
        sql = f"""
            SELECT
                {select_sql},
                toDecimal128(sum(model_cost_cents), 4) AS model_cost_cents,
                toDecimal128(sum(compute_cost_cents), 4) AS compute_cost_cents,
                toDecimal128(sum(storage_cost_cents), 4) AS storage_cost_cents,
                toDecimal128(sum(overhead_cost_cents), 4) AS overhead_cost_cents,
                toDecimal128(sum(total_cost_cents), 4) AS total_cost_cents
            FROM cost_events
            WHERE
                workspace_id IN {{workspace_ids:Array(UUID)}}
                AND occurred_at >= {{since:DateTime64}}
                AND occurred_at <= {{until:DateTime64}}
            GROUP BY {group_sql}
            ORDER BY {group_sql}
        """
        return await self._query(
            sql,
            {
                "workspace_ids": workspace_ids,
                "since": _utc(since),
                "until": _utc(until),
            },
        )

    async def query_cost_baseline(
        self,
        workspace_id: UUID,
        lookback_periods: int,
    ) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(hours=max(lookback_periods, 1))
        sql = """
            SELECT
                toStartOfHour(occurred_at) AS bucket,
                toDecimal128(sum(total_cost_cents), 4) AS total_cost_cents
            FROM cost_events
            WHERE workspace_id = {workspace_id:UUID}
              AND occurred_at >= {since:DateTime64}
            GROUP BY bucket
            ORDER BY bucket ASC
        """
        return await self._query(sql, {"workspace_id": workspace_id, "since": since})

    async def query_workspace_history(
        self,
        workspace_id: UUID,
        periods: int,
    ) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(days=max(periods, 1))
        sql = """
            SELECT
                toStartOfDay(occurred_at) AS period_start,
                toDecimal128(sum(total_cost_cents), 4) AS total_cost_cents
            FROM cost_events
            WHERE workspace_id = {workspace_id:UUID}
              AND occurred_at >= {since:DateTime64}
            GROUP BY period_start
            ORDER BY period_start ASC
        """
        return await self._query(sql, {"workspace_id": workspace_id, "since": since})

    async def _query(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return await self.client.execute_query(sql, params=params)
        except ClickHouseClientError:
            raise


def _dimension_selects(group_by: list[str]) -> list[tuple[str, str]]:
    mapping = {
        "workspace": ("workspace_id", "workspace_id"),
        "workspace_id": ("workspace_id", "workspace_id"),
        "agent": ("agent_id", "agent_id"),
        "agent_id": ("agent_id", "agent_id"),
        "user": ("user_id", "user_id"),
        "user_id": ("user_id", "user_id"),
        "cost_type": ("cost_type", "cost_type"),
        "day": ("toStartOfDay(occurred_at) AS day", "toStartOfDay(occurred_at)"),
        "week": ("toStartOfWeek(occurred_at) AS week", "toStartOfWeek(occurred_at)"),
        "month": ("toStartOfMonth(occurred_at) AS month", "toStartOfMonth(occurred_at)"),
    }
    return [mapping[item] for item in group_by if item in mapping] or [
        ("workspace_id", "workspace_id")
    ]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def cost_event_row(
    *,
    event_id: UUID,
    attribution_id: UUID,
    execution_id: UUID,
    workspace_id: UUID,
    agent_id: UUID | None,
    user_id: UUID | None,
    model_cost_cents: Decimal,
    compute_cost_cents: Decimal,
    storage_cost_cents: Decimal,
    overhead_cost_cents: Decimal,
    total_cost_cents: Decimal,
    currency: str,
    occurred_at: datetime,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "attribution_id": attribution_id,
        "execution_id": execution_id,
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "cost_type": "model" if model_cost_cents else "overhead",
        "model_cost_cents": model_cost_cents,
        "compute_cost_cents": compute_cost_cents,
        "storage_cost_cents": storage_cost_cents,
        "overhead_cost_cents": overhead_cost_cents,
        "total_cost_cents": total_cost_cents,
        "currency": currency,
        "occurred_at": _utc(occurred_at),
        "ingested_at": datetime.now(UTC),
    }
