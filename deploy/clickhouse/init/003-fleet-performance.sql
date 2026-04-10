CREATE TABLE IF NOT EXISTS fleet_performance (
    fleet_id UUID,
    metric_name String,
    metric_value Float64,
    member_count UInt16,
    measured_at DateTime64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(measured_at)
ORDER BY (fleet_id, metric_name, measured_at)
