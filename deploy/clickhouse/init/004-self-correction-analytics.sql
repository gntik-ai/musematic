CREATE TABLE IF NOT EXISTS self_correction_analytics (
    execution_id UUID,
    agent_id UUID,
    loop_id UUID,
    iterations UInt8,
    converged UInt8,
    initial_quality Float32,
    final_quality Float32,
    total_cost Decimal64(6),
    completed_at DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(completed_at)
ORDER BY (agent_id, completed_at)
