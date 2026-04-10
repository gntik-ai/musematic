CREATE MATERIALIZED VIEW IF NOT EXISTS usage_hourly_mv
TO usage_hourly AS
SELECT
    workspace_id,
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
GROUP BY workspace_id, agent_id, provider, model, hour
