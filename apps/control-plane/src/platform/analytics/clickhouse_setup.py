from __future__ import annotations

import asyncio
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from typing import Final

USAGE_EVENTS_DDL: Final[str] = """
CREATE TABLE IF NOT EXISTS analytics_usage_events
(
    event_id UUID,
    execution_id UUID,
    workspace_id UUID,
    goal_id Nullable(UUID),
    agent_fqn String,
    model_id String,
    provider String,
    timestamp DateTime64(3, 'UTC'),
    input_tokens UInt64 DEFAULT 0,
    output_tokens UInt64 DEFAULT 0,
    total_tokens UInt64 MATERIALIZED input_tokens + output_tokens,
    execution_duration_ms UInt64 DEFAULT 0,
    self_correction_loops UInt32 DEFAULT 0,
    reasoning_tokens UInt64 DEFAULT 0,
    cost_usd Decimal(18, 10) DEFAULT 0,
    pipeline_version String DEFAULT '1',
    ingested_at DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = MergeTree()
ORDER BY (toYYYYMM(timestamp), workspace_id, agent_fqn)
PARTITION BY toYYYYMM(timestamp)
TTL toDateTime(timestamp) + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192
"""

USAGE_EVENTS_GOAL_ID_DDL: Final[str] = """
ALTER TABLE analytics_usage_events
ADD COLUMN IF NOT EXISTS goal_id Nullable(UUID)
AFTER workspace_id
"""

QUALITY_EVENTS_DDL: Final[str] = """
CREATE TABLE IF NOT EXISTS analytics_quality_events
(
    event_id UUID,
    execution_id UUID,
    workspace_id UUID,
    agent_fqn String,
    model_id String,
    timestamp DateTime64(3, 'UTC'),
    quality_score Float64,
    eval_suite_id UUID DEFAULT toUUID('00000000-0000-0000-0000-000000000000'),
    ingested_at DateTime64(3, 'UTC') DEFAULT now64()
)
ENGINE = MergeTree()
ORDER BY (toYYYYMM(timestamp), workspace_id, agent_fqn)
PARTITION BY toYYYYMM(timestamp)
TTL toDateTime(timestamp) + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192
"""

USAGE_HOURLY_DDL: Final[str] = """
CREATE TABLE IF NOT EXISTS analytics_usage_hourly_v2
(
    hour DateTime,
    workspace_id UUID,
    goal_id Nullable(UUID),
    agent_fqn String,
    model_id String,
    provider String,
    execution_count_state AggregateFunction(count),
    input_tokens_state AggregateFunction(sum, UInt64),
    output_tokens_state AggregateFunction(sum, UInt64),
    cost_usd_state AggregateFunction(sum, Decimal(18, 10)),
    avg_duration_ms_state AggregateFunction(avg, UInt64),
    self_correction_loops_state AggregateFunction(sum, UInt32),
    reasoning_tokens_state AggregateFunction(sum, UInt64)
)
ENGINE = AggregatingMergeTree()
ORDER BY (hour, workspace_id, goal_id, agent_fqn, model_id)
SETTINGS allow_nullable_key = 1
"""

USAGE_HOURLY_MV_DDL: Final[str] = """
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics_usage_hourly_mv
TO analytics_usage_hourly_v2 AS
SELECT
    toStartOfHour(timestamp) AS hour,
    workspace_id,
    goal_id,
    agent_fqn,
    model_id,
    provider,
    countState() AS execution_count_state,
    sumState(input_tokens) AS input_tokens_state,
    sumState(output_tokens) AS output_tokens_state,
    sumState(cost_usd) AS cost_usd_state,
    avgState(execution_duration_ms) AS avg_duration_ms_state,
    sumState(self_correction_loops) AS self_correction_loops_state,
    sumState(reasoning_tokens) AS reasoning_tokens_state
FROM analytics_usage_events
GROUP BY hour, workspace_id, goal_id, agent_fqn, model_id, provider
"""

USAGE_DAILY_DDL: Final[str] = """
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics_usage_daily
ENGINE = AggregatingMergeTree()
ORDER BY (day, workspace_id, agent_fqn, model_id)
POPULATE AS
SELECT
    toStartOfDay(timestamp) AS day,
    workspace_id,
    agent_fqn,
    model_id,
    provider,
    countState() AS execution_count_state,
    sumState(input_tokens) AS input_tokens_state,
    sumState(output_tokens) AS output_tokens_state,
    sumState(cost_usd) AS cost_usd_state,
    avgState(execution_duration_ms) AS avg_duration_ms_state,
    sumState(self_correction_loops) AS self_correction_loops_state
FROM analytics_usage_events
GROUP BY day, workspace_id, agent_fqn, model_id, provider
"""

USAGE_MONTHLY_DDL: Final[str] = """
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics_usage_monthly
ENGINE = AggregatingMergeTree()
ORDER BY (month, workspace_id, agent_fqn, model_id)
POPULATE AS
SELECT
    toStartOfMonth(timestamp) AS month,
    workspace_id,
    agent_fqn,
    model_id,
    provider,
    countState() AS execution_count_state,
    sumState(input_tokens) AS input_tokens_state,
    sumState(output_tokens) AS output_tokens_state,
    sumState(cost_usd) AS cost_usd_state,
    avgState(execution_duration_ms) AS avg_duration_ms_state,
    sumState(self_correction_loops) AS self_correction_loops_state
FROM analytics_usage_events
GROUP BY month, workspace_id, agent_fqn, model_id, provider
"""


async def run_setup(
    client: AsyncClickHouseClient | None = None,
    settings: PlatformSettings | None = None,
) -> None:
    resolved_settings = settings or default_settings
    resolved_client = client or AsyncClickHouseClient.from_settings(resolved_settings)
    should_close = client is None
    if should_close:
        await resolved_client.connect()
    try:
        for statement in (
            USAGE_EVENTS_DDL,
            USAGE_EVENTS_GOAL_ID_DDL,
            QUALITY_EVENTS_DDL,
            USAGE_HOURLY_DDL,
            USAGE_HOURLY_MV_DDL,
            USAGE_DAILY_DDL,
            USAGE_MONTHLY_DDL,
        ):
            await resolved_client.execute_command(statement)
    finally:
        if should_close:
            await resolved_client.close()


def main() -> None:
    asyncio.run(run_setup())


if __name__ == "__main__":
    main()
