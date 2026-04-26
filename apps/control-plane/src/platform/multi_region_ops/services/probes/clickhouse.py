from __future__ import annotations

from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.services.probes.base import ReplicationMeasurement
from typing import Any


class ClickHouseReplicationProbe:
    component = "clickhouse"

    def __init__(self, clickhouse_client: AsyncClickHouseClient | None) -> None:
        self.clickhouse_client = clickhouse_client

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del source, target
        if self.clickhouse_client is None:
            return ReplicationMeasurement(
                component=self.component,
                lag_seconds=None,
                health="unhealthy",
                error_detail="clickhouse client unavailable",
            )
        rows = await self.clickhouse_client.execute_query(
            """
            SELECT
                max(dateDiff('second', create_time, now())) AS lag_seconds,
                max(queue_size) AS queue_size
            FROM system.replication_queue
            """
        )
        row: dict[str, Any] = rows[0] if rows else {}
        lag = _as_int(row.get("lag_seconds"))
        queue_size = _as_int(row.get("queue_size")) or 0
        health = "healthy" if queue_size == 0 else "degraded" if queue_size < 100 else "unhealthy"
        return ReplicationMeasurement(component=self.component, lag_seconds=lag, health=health)


def _as_int(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return None
    return None
