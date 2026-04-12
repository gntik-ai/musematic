CREATE TABLE IF NOT EXISTS testing_drift_metrics
(
    run_id String,
    workspace_id String,
    agent_fqn String,
    eval_set_id String,
    score Float64,
    measured_at DateTime64(3, 'UTC')
)
ENGINE = MergeTree
ORDER BY (workspace_id, agent_fqn, eval_set_id, measured_at);
