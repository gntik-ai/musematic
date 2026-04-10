CREATE TABLE IF NOT EXISTS behavioral_drift (
    agent_id UUID,
    revision_id UUID,
    metric_name String,
    metric_value Float64,
    baseline_value Float64,
    deviation Float64,
    measured_at DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(measured_at)
ORDER BY (agent_id, metric_name, measured_at)
TTL measured_at + INTERVAL 180 DAY
