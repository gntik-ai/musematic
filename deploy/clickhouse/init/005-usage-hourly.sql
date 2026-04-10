CREATE TABLE IF NOT EXISTS usage_hourly (
    workspace_id UUID,
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
)
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(hour)
ORDER BY (workspace_id, agent_id, provider, model, hour)
