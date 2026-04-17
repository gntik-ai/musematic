package state

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

type fakeQueryExecutor struct {
	execSQL   []string
	execErr   error
	querySQL  []string
	queryErr  error
	queryRows pgx.Rows
	queryRow  pgx.Row
	closeHits int
}

func (f *fakeQueryExecutor) Exec(_ context.Context, sql string, _ ...any) (pgconn.CommandTag, error) {
	f.execSQL = append(f.execSQL, sql)
	return pgconn.NewCommandTag("OK"), f.execErr
}

func (f *fakeQueryExecutor) Query(_ context.Context, sql string, _ ...any) (pgx.Rows, error) {
	f.querySQL = append(f.querySQL, sql)
	if f.queryErr != nil {
		return nil, f.queryErr
	}
	return f.queryRows, nil
}

func (f *fakeQueryExecutor) QueryRow(_ context.Context, sql string, _ ...any) pgx.Row {
	f.querySQL = append(f.querySQL, sql)
	return f.queryRow
}

func (f *fakeQueryExecutor) Ping(context.Context) error { return nil }

func (f *fakeQueryExecutor) Close() { f.closeHits++ }

type fakeRow struct {
	values []any
	err    error
}

func (r fakeRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	return assignScanValues(dest, r.values)
}

type fakeRows struct {
	rows    [][]any
	index   int
	closed  bool
	err     error
	scanErr error
}

func (r *fakeRows) Close() { r.closed = true }

func (r *fakeRows) Err() error { return r.err }

func (r *fakeRows) CommandTag() pgconn.CommandTag { return pgconn.NewCommandTag("SELECT 1") }

func (r *fakeRows) FieldDescriptions() []pgconn.FieldDescription { return nil }

func (r *fakeRows) Next() bool {
	if r.index >= len(r.rows) {
		return false
	}
	r.index++
	return true
}

func (r *fakeRows) Scan(dest ...any) error {
	if r.index == 0 || r.index > len(r.rows) {
		return fmt.Errorf("scan called without current row")
	}
	if r.scanErr != nil {
		return r.scanErr
	}
	return assignScanValues(dest, r.rows[r.index-1])
}

func (r *fakeRows) Values() ([]any, error) {
	if r.index == 0 || r.index > len(r.rows) {
		return nil, fmt.Errorf("values called without current row")
	}
	return r.rows[r.index-1], nil
}

func (r *fakeRows) RawValues() [][]byte { return nil }

func (r *fakeRows) Conn() *pgx.Conn { return nil }

func assignScanValues(dest []any, values []any) error {
	if len(dest) != len(values) {
		return fmt.Errorf("unexpected scan widths %d != %d", len(dest), len(values))
	}
	for index := range dest {
		if err := assignValue(dest[index], values[index]); err != nil {
			return err
		}
	}
	return nil
}

func assignValue(dest any, src any) error {
	rv := reflect.ValueOf(dest)
	if rv.Kind() != reflect.Ptr || rv.IsNil() {
		return fmt.Errorf("destination must be pointer")
	}
	target := rv.Elem()
	if src == nil {
		target.Set(reflect.Zero(target.Type()))
		return nil
	}
	if target.Kind() == reflect.Ptr {
		elem := reflect.New(target.Type().Elem())
		if err := assignValue(elem.Interface(), src); err != nil {
			return err
		}
		target.Set(elem)
		return nil
	}
	value := reflect.ValueOf(src)
	if value.Type().AssignableTo(target.Type()) {
		target.Set(value)
		return nil
	}
	if value.Type().ConvertibleTo(target.Type()) {
		target.Set(value.Convert(target.Type()))
		return nil
	}
	return fmt.Errorf("cannot assign %T to %T", src, dest)
}

func TestStateQueries(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	totalDuration := int64(1500)
	sandboxID := uuid.New()
	eventID := uuid.New()

	executor := &fakeQueryExecutor{
		queryRow: fakeRow{
			values: []any{
				sandboxID, "exec-1", "ws-1", "python3.12", "ready", "",
				"sandbox-pod", "platform-execution", json.RawMessage(`{"cpu":"250m"}`), true,
				int32(3), totalDuration, now, now, nil, now,
			},
		},
		queryRows: &fakeRows{
			rows: [][]any{{
				eventID, sandboxID, "exec-1", "sandbox.ready", json.RawMessage(`{"state":"ready"}`), now,
			}},
		},
	}
	store := newStoreForQueries(executor)

	if err := store.InsertSandbox(context.Background(), SandboxRecord{
		SandboxID:      sandboxID,
		ExecutionID:    "exec-1",
		WorkspaceID:    "ws-1",
		Template:       "python3.12",
		State:          "creating",
		PodName:        "sandbox-pod",
		PodNamespace:   "platform-execution",
		ResourceLimits: json.RawMessage(`{"cpu":"250m"}`),
		NetworkEnabled: true,
		CreatedAt:      now,
		UpdatedAt:      now,
	}); err != nil {
		t.Fatalf("InsertSandbox() error = %v", err)
	}
	if err := store.UpdateSandboxState(context.Background(), sandboxID.String(), "ready", "", 3, &totalDuration); err != nil {
		t.Fatalf("UpdateSandboxState() error = %v", err)
	}
	record, err := store.GetSandbox(context.Background(), sandboxID.String())
	if err != nil {
		t.Fatalf("GetSandbox() error = %v", err)
	}
	if record.ExecutionID != "exec-1" || record.State != "ready" {
		t.Fatalf("unexpected sandbox record %+v", record)
	}
	if err := store.InsertSandboxEvent(context.Background(), SandboxEventRecord{
		EventID:     eventID,
		SandboxID:   sandboxID,
		ExecutionID: "exec-1",
		EventType:   "sandbox.ready",
		Payload:     json.RawMessage(`{"state":"ready"}`),
		EmittedAt:   now,
	}); err != nil {
		t.Fatalf("InsertSandboxEvent() error = %v", err)
	}
	events, err := store.GetSandboxEventsSince(context.Background(), sandboxID.String(), now.Add(-time.Minute))
	if err != nil {
		t.Fatalf("GetSandboxEventsSince() error = %v", err)
	}
	if len(events) != 1 || events[0].EventType != "sandbox.ready" {
		t.Fatalf("unexpected events %+v", events)
	}

	if len(executor.execSQL) != 3 {
		t.Fatalf("unexpected exec count %d", len(executor.execSQL))
	}
	if len(executor.querySQL) != 2 {
		t.Fatalf("unexpected query count %d", len(executor.querySQL))
	}
	if !strings.Contains(executor.execSQL[0], "INSERT INTO sandboxes") {
		t.Fatalf("unexpected first exec SQL %q", executor.execSQL[0])
	}
}

func TestGetSandboxMapsNotFound(t *testing.T) {
	t.Parallel()

	store := newStoreForQueries(&fakeQueryExecutor{
		queryRow: fakeRow{err: pgx.ErrNoRows},
	})
	if _, err := store.GetSandbox(context.Background(), uuid.NewString()); err != ErrNotFound {
		t.Fatalf("GetSandbox() error = %v", err)
	}

	store = newStoreForQueries(&fakeQueryExecutor{
		queryRow: fakeRow{err: errors.New("no rows in result set")},
	})
	if _, err := store.GetSandbox(context.Background(), uuid.NewString()); err != ErrNotFound {
		t.Fatalf("GetSandbox() string error = %v", err)
	}
}

func TestRunMigrationsAndHelpers(t *testing.T) {
	t.Parallel()

	executor := &fakeQueryExecutor{}
	if err := RunMigrations(context.Background(), executor); err != nil {
		t.Fatalf("RunMigrations() error = %v", err)
	}
	if len(executor.execSQL) != len(migrationStatements) {
		t.Fatalf("unexpected migration exec count %d", len(executor.execSQL))
	}
	if got := MarshalResourceLimits(nil); string(got) != "{}" {
		t.Fatalf("MarshalResourceLimits(nil) = %s", string(got))
	}
	if got := MarshalResourceLimits(map[string]string{"cpu": "250m"}); string(got) == "" {
		t.Fatal("expected marshalled resource limits")
	}
	if got := MarshalResourceLimits(map[string]any{"bad": make(chan int)}); string(got) != "{}" {
		t.Fatalf("MarshalResourceLimits(invalid) = %s", string(got))
	}
	if got := nullableTime(time.Time{}); got != nil {
		t.Fatalf("nullableTime(zero) = %v", got)
	}
	now := time.Now().UTC()
	if got := nullableTime(now); got == nil || !got.Equal(now) {
		t.Fatalf("nullableTime(now) = %v", got)
	}

	store := newStoreForQueries(executor)
	if store.Pool() != nil {
		t.Fatalf("expected nil pgx pool, got %v", store.Pool())
	}
	store.Close()
	if executor.closeHits != 1 {
		t.Fatalf("expected Close() to hit executor once, got %d", executor.closeHits)
	}
}

func TestNewStoreRejectsInvalidDSNAndCloseHandlesNil(t *testing.T) {
	t.Parallel()

	if _, err := NewStore(context.Background(), "://bad dsn"); err == nil {
		t.Fatal("expected NewStore() to fail for invalid dsn")
	}

	store := &Store{}
	store.Close()
}

func TestNewStoreAcceptsValidDSNAndClosesPool(t *testing.T) {
	t.Parallel()

	store, err := NewStore(context.Background(), "postgres://sandbox:test@127.0.0.1:1/musematic?sslmode=disable&connect_timeout=1")
	if err != nil {
		t.Fatalf("NewStore() error = %v", err)
	}
	if store == nil || store.Pool() == nil {
		t.Fatalf("expected NewStore() to initialize a pool, got %+v", store)
	}
	store.Close()
}

func TestStateQueryErrors(t *testing.T) {
	t.Parallel()

	expectedErr := errors.New("query boom")
	store := newStoreForQueries(&fakeQueryExecutor{
		queryRow:  fakeRow{err: expectedErr},
		queryErr:  expectedErr,
		queryRows: &fakeRows{err: expectedErr},
	})

	if _, err := store.GetSandbox(context.Background(), uuid.NewString()); !errors.Is(err, expectedErr) {
		t.Fatalf("GetSandbox() error = %v, want %v", err, expectedErr)
	}
	if _, err := store.GetSandboxEventsSince(context.Background(), uuid.NewString(), time.Now().UTC()); !errors.Is(err, expectedErr) {
		t.Fatalf("GetSandboxEventsSince() error = %v, want %v", err, expectedErr)
	}

	rowsErrStore := newStoreForQueries(&fakeQueryExecutor{
		queryRows: &fakeRows{
			rows: [][]any{{uuid.New(), uuid.New(), "exec-1", "sandbox.ready", json.RawMessage(`{}`), time.Now().UTC()}},
			err:  expectedErr,
		},
	})
	if _, err := rowsErrStore.GetSandboxEventsSince(context.Background(), uuid.NewString(), time.Now().UTC()); !errors.Is(err, expectedErr) {
		t.Fatalf("GetSandboxEventsSince() rows error = %v, want %v", err, expectedErr)
	}

	scanErrStore := newStoreForQueries(&fakeQueryExecutor{
		queryRows: &fakeRows{
			rows:    [][]any{{uuid.New(), uuid.New(), "exec-1", "sandbox.ready", json.RawMessage(`{}`), time.Now().UTC()}},
			scanErr: expectedErr,
		},
	})
	if _, err := scanErrStore.GetSandboxEventsSince(context.Background(), uuid.NewString(), time.Now().UTC()); !errors.Is(err, expectedErr) {
		t.Fatalf("GetSandboxEventsSince() scan error = %v, want %v", err, expectedErr)
	}
}

func TestRunMigrationsStopsOnExecError(t *testing.T) {
	t.Parallel()

	expectedErr := errors.New("exec boom")
	executor := &fakeQueryExecutor{execErr: expectedErr}
	if err := RunMigrations(context.Background(), executor); !errors.Is(err, expectedErr) {
		t.Fatalf("RunMigrations() error = %v, want %v", err, expectedErr)
	}
	if len(executor.execSQL) != 1 {
		t.Fatalf("expected RunMigrations() to stop after first failure, got %d statements", len(executor.execSQL))
	}
}
