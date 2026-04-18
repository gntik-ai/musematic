package state

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

var migrationStatements = []string{
	`
CREATE TABLE IF NOT EXISTS runtimes (
    runtime_id UUID PRIMARY KEY,
    execution_id TEXT NOT NULL UNIQUE,
    step_id TEXT,
    workspace_id TEXT NOT NULL,
    agent_fqn TEXT NOT NULL,
    agent_revision TEXT NOT NULL,
    model_binding JSONB NOT NULL,
    state TEXT NOT NULL,
    failure_reason TEXT,
    pod_name TEXT,
    pod_namespace TEXT NOT NULL DEFAULT 'platform-execution',
    correlation_context JSONB NOT NULL,
    resource_limits JSONB NOT NULL,
    secret_refs TEXT[],
    launched_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    last_heartbeat_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)`,
	`CREATE INDEX IF NOT EXISTS idx_runtimes_execution_id ON runtimes (execution_id)`,
	`CREATE INDEX IF NOT EXISTS idx_runtimes_workspace_state ON runtimes (workspace_id, state)`,
	`CREATE INDEX IF NOT EXISTS idx_runtimes_state ON runtimes (state)`,
	`
CREATE TABLE IF NOT EXISTS warm_pool_pods (
    pod_id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    pod_name TEXT NOT NULL UNIQUE,
    pod_namespace TEXT NOT NULL DEFAULT 'platform-execution',
    status TEXT NOT NULL,
    dispatched_to UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ready_at TIMESTAMPTZ,
    idle_since TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ
)`,
	`CREATE INDEX IF NOT EXISTS idx_warm_pool_ready ON warm_pool_pods (workspace_id, agent_type, status)`,
	`
CREATE TABLE IF NOT EXISTS runtime_warm_pool_targets (
    id UUID PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    target_size INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_runtime_warm_pool_target_key UNIQUE (workspace_id, agent_type)
)`,
	`CREATE INDEX IF NOT EXISTS idx_runtime_warm_pool_targets_lookup ON runtime_warm_pool_targets (workspace_id, agent_type)`,
	`
CREATE TABLE IF NOT EXISTS task_plan_records (
    record_id UUID PRIMARY KEY,
    execution_id TEXT NOT NULL,
    step_id TEXT,
    workspace_id TEXT NOT NULL,
    considered_agents JSONB,
    selected_agent TEXT,
    selection_rationale TEXT,
    parameters JSONB,
    parameter_provenance JSONB,
    payload_json JSONB,
    payload_object_key TEXT,
    persisted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)`,
	`CREATE INDEX IF NOT EXISTS idx_task_plans_execution_id ON task_plan_records (execution_id)`,
	`
CREATE TABLE IF NOT EXISTS runtime_events (
    event_id UUID PRIMARY KEY,
    runtime_id UUID NOT NULL,
    execution_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    emitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)`,
	`CREATE INDEX IF NOT EXISTS idx_runtime_events_runtime_emitted ON runtime_events (runtime_id, emitted_at DESC)`,
}

func RunMigrations(ctx context.Context, pool *pgxpool.Pool) error {
	for _, stmt := range migrationStatements {
		if _, err := pool.Exec(ctx, stmt); err != nil {
			return err
		}
	}
	return nil
}
