from __future__ import annotations

from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.config import PlatformSettings


async def run_setup(
    client: AsyncClickHouseClient,
    settings: PlatformSettings | None = None,
) -> None:
    del settings
    for statement in _ddl_statements():
        await client.execute_command(statement)


def _ddl_statements() -> list[str]:
    return [
        """
        CREATE TABLE IF NOT EXISTS cost_events (
            event_id UUID,
            attribution_id UUID,
            execution_id UUID,
            workspace_id UUID,
            agent_id Nullable(UUID),
            user_id Nullable(UUID),
            cost_type LowCardinality(String),
            model_cost_cents Decimal(14, 4),
            compute_cost_cents Decimal(14, 4),
            storage_cost_cents Decimal(14, 4),
            overhead_cost_cents Decimal(14, 4),
            total_cost_cents Decimal(14, 4),
            currency LowCardinality(String),
            occurred_at DateTime64(3, 'UTC'),
            ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
        )
        ENGINE = MergeTree()
        PARTITION BY toYYYYMM(occurred_at)
        ORDER BY (workspace_id, occurred_at)
        TTL occurred_at + INTERVAL 730 DAY
        """,
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS cost_hourly_by_workspace
        ENGINE = AggregatingMergeTree()
        PARTITION BY toYYYYMM(hour)
        ORDER BY (workspace_id, hour)
        AS
        SELECT
            workspace_id,
            toStartOfHour(occurred_at) AS hour,
            sumState(model_cost_cents) AS model_cost_cents_state,
            sumState(compute_cost_cents) AS compute_cost_cents_state,
            sumState(storage_cost_cents) AS storage_cost_cents_state,
            sumState(overhead_cost_cents) AS overhead_cost_cents_state,
            sumState(total_cost_cents) AS total_cost_cents_state,
            countState() AS event_count_state
        FROM cost_events
        GROUP BY workspace_id, hour
        """,
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS cost_daily_by_workspace_agent
        ENGINE = AggregatingMergeTree()
        PARTITION BY toYYYYMM(day)
        ORDER BY (workspace_id, agent_id, day)
        AS
        SELECT
            workspace_id,
            agent_id,
            toStartOfDay(occurred_at) AS day,
            sumState(model_cost_cents) AS model_cost_cents_state,
            sumState(compute_cost_cents) AS compute_cost_cents_state,
            sumState(storage_cost_cents) AS storage_cost_cents_state,
            sumState(overhead_cost_cents) AS overhead_cost_cents_state,
            sumState(total_cost_cents) AS total_cost_cents_state,
            countState() AS event_count_state
        FROM cost_events
        GROUP BY workspace_id, agent_id, day
        """,
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS cost_daily_by_workspace_user
        ENGINE = AggregatingMergeTree()
        PARTITION BY toYYYYMM(day)
        ORDER BY (workspace_id, user_id, day)
        AS
        SELECT
            workspace_id,
            user_id,
            toStartOfDay(occurred_at) AS day,
            sumState(model_cost_cents) AS model_cost_cents_state,
            sumState(compute_cost_cents) AS compute_cost_cents_state,
            sumState(storage_cost_cents) AS storage_cost_cents_state,
            sumState(overhead_cost_cents) AS overhead_cost_cents_state,
            sumState(total_cost_cents) AS total_cost_cents_state,
            countState() AS event_count_state
        FROM cost_events
        GROUP BY workspace_id, user_id, day
        """,
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS cost_daily_by_cost_type
        ENGINE = AggregatingMergeTree()
        PARTITION BY toYYYYMM(day)
        ORDER BY (workspace_id, cost_type, day)
        AS
        SELECT
            workspace_id,
            cost_type,
            toStartOfDay(occurred_at) AS day,
            sumState(model_cost_cents) AS model_cost_cents_state,
            sumState(compute_cost_cents) AS compute_cost_cents_state,
            sumState(storage_cost_cents) AS storage_cost_cents_state,
            sumState(overhead_cost_cents) AS overhead_cost_cents_state,
            sumState(total_cost_cents) AS total_cost_cents_state,
            countState() AS event_count_state
        FROM cost_events
        GROUP BY workspace_id, cost_type, day
        """,
    ]

