CREATE TABLE IF NOT EXISTS usage_events (
    event_id UUID,
    workspace_id UUID,
    user_id UUID,
    agent_id UUID,
    workflow_id Nullable(UUID),
    execution_id Nullable(UUID),
    provider String,
    model String,
    input_tokens UInt32,
    output_tokens UInt32,
    reasoning_tokens UInt32 DEFAULT 0,
    cached_tokens UInt32 DEFAULT 0,
    estimated_cost Decimal64(6),
    context_quality_score Nullable(Float32),
    reasoning_depth Nullable(UInt8),
    event_time DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (workspace_id, event_time, agent_id)
TTL event_time + INTERVAL 365 DAY
