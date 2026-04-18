ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS goal_id Nullable(UUID);

CREATE TABLE IF NOT EXISTS usage_hourly_v2 (
    workspace_id UUID,
    goal_id Nullable(UUID),
    agent_id UUID,
    provider String,
    model String,
    hour DateTime,
    total_input_tokens UInt64,
    total_output_tokens UInt64,
    total_reasoning_tokens UInt64,
    total_cost Decimal128(6),
    event_count UInt64,
    avg_context_quality Float64
) ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (workspace_id, goal_id, agent_id, provider, model, hour)
SETTINGS allow_nullable_key = 1;

DROP VIEW IF EXISTS usage_hourly_mv;

CREATE MATERIALIZED VIEW IF NOT EXISTS usage_hourly_mv TO usage_hourly_v2 AS
SELECT
    workspace_id,
    goal_id,
    agent_id,
    provider,
    model,
    toStartOfHour(event_time) AS hour,
    sum(input_tokens) AS total_input_tokens,
    sum(output_tokens) AS total_output_tokens,
    sum(reasoning_tokens) AS total_reasoning_tokens,
    sum(estimated_cost) AS total_cost,
    count() AS event_count,
    avg(context_quality_score) AS avg_context_quality
FROM usage_events
GROUP BY workspace_id, goal_id, agent_id, provider, model, hour;
