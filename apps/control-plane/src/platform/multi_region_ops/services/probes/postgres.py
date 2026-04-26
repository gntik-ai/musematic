from __future__ import annotations

from datetime import timedelta
from platform.common.clients.model_router import SecretProvider
from platform.multi_region_ops.models import RegionConfig
from platform.multi_region_ops.services.probes.base import ReplicationMeasurement
from typing import Any


class PostgresReplicationProbe:
    component = "postgres"

    def __init__(self, secret_provider: SecretProvider) -> None:
        self.secret_provider = secret_provider

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del target
        dsn_ref = source.endpoint_urls.get("postgres_replica_dsn_ref")
        if not isinstance(dsn_ref, str) or not dsn_ref:
            return ReplicationMeasurement(
                component=self.component,
                lag_seconds=None,
                health="unhealthy",
                error_detail="postgres_replica_dsn_ref missing",
            )
        dsn = await self.secret_provider.get_current(dsn_ref)
        asyncpg = __import__("asyncpg")
        connection = await asyncpg.connect(dsn)
        try:
            rows = await connection.fetch(
                """
                SELECT state, replay_lag
                FROM pg_stat_replication
                ORDER BY replay_lag DESC NULLS LAST
                LIMIT 1
                """
            )
        finally:
            await connection.close()
        if not rows:
            return ReplicationMeasurement(
                component=self.component,
                lag_seconds=None,
                health="unhealthy",
                error_detail="pg_stat_replication returned no rows",
            )
        row: Any = rows[0]
        state = str(row.get("state") if hasattr(row, "get") else row["state"])
        lag_value = row.get("replay_lag") if hasattr(row, "get") else row["replay_lag"]
        lag_seconds = _interval_to_seconds(lag_value)
        health = (
            "healthy" if state == "streaming" else "degraded" if state == "catchup" else "unhealthy"
        )
        return ReplicationMeasurement(
            component=self.component,
            lag_seconds=lag_seconds,
            health=health,
            error_detail=None if health != "unhealthy" else f"replication state={state}",
        )


def _interval_to_seconds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    try:
        parts = [float(part) for part in text.split(":")]
    except ValueError:
        return None
    if len(parts) == 3:
        return int(parts[0] * 3600 + parts[1] * 60 + parts[2])
    return None
