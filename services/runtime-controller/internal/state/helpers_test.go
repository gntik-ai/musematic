package state

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
)

func TestNewStoreAndHelpers(t *testing.T) {
	if _, err := NewStore(context.Background(), "://bad-dsn"); err == nil {
		t.Fatalf("expected invalid DSN error")
	}

	store := &Store{}
	if store.Pool() != nil {
		t.Fatalf("expected nil pool")
	}
	store.Close()

	if got := nilIfEmpty(""); got != nil {
		t.Fatalf("expected nil for empty string, got %#v", got)
	}
	if got := nilIfEmpty("value"); got != "value" {
		t.Fatalf("expected original value, got %#v", got)
	}
	if got := nullJSON(nil); got != nil {
		t.Fatalf("expected nil for empty json, got %#v", got)
	}
	payload := json.RawMessage(`{"ok":true}`)
	if got := nullJSON(payload); string(got.(json.RawMessage)) != string(payload) {
		t.Fatalf("unexpected json payload: %#v", got)
	}
	if got := zeroTimeToNil(time.Time{}); got != nil {
		t.Fatalf("expected nil for zero time, got %#v", got)
	}
	now := time.Now().UTC()
	if got := zeroTimeToNil(now); got != now {
		t.Fatalf("expected time value, got %#v", got)
	}
	if !IsNotFound(pgx.ErrNoRows) {
		t.Fatalf("expected pgx.ErrNoRows to be treated as not found")
	}
	if IsNotFound(context.Canceled) {
		t.Fatalf("did not expect unrelated error to be treated as not found")
	}
}

func TestMigrationStatementsContainWarmPoolTargets(t *testing.T) {
	foundTable := false
	foundIndex := false
	for _, stmt := range migrationStatements {
		if strings.Contains(stmt, "CREATE TABLE IF NOT EXISTS runtime_warm_pool_targets") {
			foundTable = true
		}
		if strings.Contains(stmt, "idx_runtime_warm_pool_targets_lookup") {
			foundIndex = true
		}
	}
	if !foundTable || !foundIndex {
		t.Fatalf("expected warm pool target migration statements, foundTable=%v foundIndex=%v", foundTable, foundIndex)
	}
}
