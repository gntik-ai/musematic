package state

import (
	"context"

	"github.com/jackc/pgx/v5/pgconn"
)

var migrationStatements = []string{
	`
CREATE TABLE IF NOT EXISTS sandboxes (
    sandbox_id UUID PRIMARY KEY,
    execution_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    template TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('creating', 'ready', 'executing', 'completed', 'failed', 'terminated')),
    failure_reason TEXT,
    pod_name TEXT,
    pod_namespace TEXT NOT NULL DEFAULT 'platform-execution',
    resource_limits JSONB NOT NULL,
    network_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    total_steps INT NOT NULL DEFAULT 0,
    total_duration_ms BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ready_at TIMESTAMPTZ,
    terminated_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)`,
	`CREATE INDEX IF NOT EXISTS idx_sandboxes_execution_id ON sandboxes (execution_id)`,
	`CREATE INDEX IF NOT EXISTS idx_sandboxes_workspace_state ON sandboxes (workspace_id, state)`,
	`CREATE INDEX IF NOT EXISTS idx_sandboxes_state ON sandboxes (state)`,
	`
CREATE TABLE IF NOT EXISTS sandbox_events (
    event_id UUID PRIMARY KEY,
    sandbox_id UUID NOT NULL,
    execution_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    emitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)`,
	`CREATE INDEX IF NOT EXISTS idx_sandbox_events_sandbox_emitted ON sandbox_events (sandbox_id, emitted_at DESC)`,
}

type migrationExecutor interface {
	Exec(context.Context, string, ...any) (pgconn.CommandTag, error)
}

func RunMigrations(ctx context.Context, pool migrationExecutor) error {
	for _, stmt := range migrationStatements {
		if _, err := pool.Exec(ctx, stmt); err != nil {
			return err
		}
	}
	return nil
}
