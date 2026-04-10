//go:build integration

package state

import (
	"context"
	"os"
	"testing"

	"github.com/google/uuid"
)

func TestRunMigrationsAndInsertSandbox(t *testing.T) {
	dsn := os.Getenv("POSTGRES_DSN")
	if dsn == "" {
		t.Skip("POSTGRES_DSN is required for integration tests")
	}
	ctx := context.Background()
	store, err := NewStore(ctx, dsn)
	if err != nil {
		t.Fatalf("new store: %v", err)
	}
	defer store.Close()
	if err := RunMigrations(ctx, store.Pool()); err != nil {
		t.Fatalf("run migrations: %v", err)
	}
	record := SandboxRecord{
		SandboxID:      uuid.New(),
		ExecutionID:    uuid.NewString(),
		WorkspaceID:    "ws-integration",
		Template:       "python3.12",
		State:          "creating",
		PodName:        "sandbox-test",
		PodNamespace:   "platform-execution",
		ResourceLimits: MarshalResourceLimits(map[string]string{"cpu_limit": "500m"}),
	}
	if err := store.InsertSandbox(ctx, record); err != nil {
		t.Fatalf("insert sandbox: %v", err)
	}
	if err := store.UpdateSandboxState(ctx, record.SandboxID.String(), "ready", "", 1, nil); err != nil {
		t.Fatalf("update sandbox: %v", err)
	}
	loaded, err := store.GetSandbox(ctx, record.SandboxID.String())
	if err != nil {
		t.Fatalf("get sandbox: %v", err)
	}
	if loaded.State != "ready" {
		t.Fatalf("expected ready state, got %s", loaded.State)
	}
}
