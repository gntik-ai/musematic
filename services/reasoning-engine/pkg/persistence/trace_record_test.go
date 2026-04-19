package persistence

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

type fakeTraceQuerier struct {
	execSQL   string
	execArgs  []any
	execErr   error
	row       pgx.Row
	querySQL  string
	queryArgs []any
}

func (q *fakeTraceQuerier) Exec(_ context.Context, sql string, arguments ...any) (pgconn.CommandTag, error) {
	q.execSQL = sql
	q.execArgs = arguments
	return pgconn.CommandTag{}, q.execErr
}

func (q *fakeTraceQuerier) QueryRow(_ context.Context, sql string, args ...any) pgx.Row {
	q.querySQL = sql
	q.queryArgs = args
	if q.row != nil {
		return q.row
	}
	return fakeRow{err: pgx.ErrNoRows}
}

type fakeRow struct {
	record ReasoningTraceRecord
	err    error
}

func (r fakeRow) Scan(dest ...any) error {
	if r.err != nil {
		return r.err
	}
	*(dest[0].(*string)) = r.record.ExecutionID
	*(dest[1].(*string)) = r.record.StepID
	*(dest[2].(*string)) = r.record.Technique
	*(dest[3].(*string)) = r.record.StorageKey
	*(dest[4].(*int)) = r.record.StepCount
	*(dest[5].(*string)) = r.record.Status
	*(dest[6].(*float64)) = r.record.ComputeBudgetUsed
	if r.record.ConsensusReached != nil {
		*(dest[7].(**bool)) = r.record.ConsensusReached
	}
	if r.record.Stabilized != nil {
		*(dest[8].(**bool)) = r.record.Stabilized
	}
	if r.record.DegradationDetected != nil {
		*(dest[9].(**bool)) = r.record.DegradationDetected
	}
	*(dest[10].(*bool)) = r.record.ComputeBudgetExhausted
	*(dest[11].(*string)) = r.record.EffectiveBudgetScope
	*(dest[12].(*time.Time)) = r.record.CreatedAt
	*(dest[13].(*time.Time)) = r.record.UpdatedAt
	return nil
}

func boolPtr(value bool) *bool { return &value }

func TestInsertTraceRecordAndStoreHelpers(t *testing.T) {
	query := &fakeTraceQuerier{}
	record := ReasoningTraceRecord{
		ExecutionID:            "exec-1",
		Technique:              "DEBATE",
		StorageKey:             "reasoning-debates/exec-1/deb-1/trace.json",
		StepCount:              4,
		ComputeBudgetUsed:      0.4,
		ConsensusReached:       boolPtr(true),
		ComputeBudgetExhausted: false,
	}
	if err := InsertTraceRecord(context.Background(), query, record); err != nil {
		t.Fatalf("InsertTraceRecord() error = %v", err)
	}
	if query.execSQL == "" || len(query.execArgs) != 12 {
		t.Fatalf("unexpected exec call: sql=%q args=%d", query.execSQL, len(query.execArgs))
	}
	if query.execArgs[1] != nil {
		t.Fatalf("step id arg = %#v, want nil for empty step", query.execArgs[1])
	}
	if query.execArgs[5] != "complete" {
		t.Fatalf("status arg = %#v, want complete", query.execArgs[5])
	}

	store := NewTraceRecordStore(nil)
	if store != nil {
		t.Fatal("NewTraceRecordStore(nil) should return nil")
	}
	var nilStore *PostgresTraceStore
	if err := nilStore.InsertTraceRecord(context.Background(), record); err != nil {
		t.Fatalf("nil store InsertTraceRecord() error = %v", err)
	}
	if _, err := nilStore.GetTraceRecord(context.Background(), "exec-1", ""); !errors.Is(err, pgx.ErrNoRows) {
		t.Fatalf("nil store GetTraceRecord() error = %v", err)
	}
}

func TestGetTraceRecord(t *testing.T) {
	created := time.Date(2026, time.April, 19, 12, 0, 0, 0, time.UTC)
	updated := created.Add(time.Minute)
	record := ReasoningTraceRecord{
		ExecutionID:            "exec-1",
		StepID:                 "step-1",
		Technique:              "SELF_CORRECTION",
		StorageKey:             "reasoning-corrections/exec-1/step-1/trace.json",
		StepCount:              9,
		Status:                 "in_progress",
		ComputeBudgetUsed:      0.65,
		ConsensusReached:       boolPtr(false),
		Stabilized:             boolPtr(true),
		DegradationDetected:    boolPtr(false),
		ComputeBudgetExhausted: true,
		EffectiveBudgetScope:   "step",
		CreatedAt:              created,
		UpdatedAt:              updated,
	}
	query := &fakeTraceQuerier{row: fakeRow{record: record}}
	loaded, err := GetTraceRecord(context.Background(), query, "exec-1", "step-1")
	if err != nil {
		t.Fatalf("GetTraceRecord() error = %v", err)
	}
	if loaded.Technique != record.Technique || loaded.StepID != record.StepID || loaded.Stabilized == nil || !*loaded.Stabilized || loaded.EffectiveBudgetScope != "step" {
		t.Fatalf("loaded record = %+v", loaded)
	}
	if len(query.queryArgs) != 2 || query.queryArgs[1] != "step-1" {
		t.Fatalf("query args = %+v", query.queryArgs)
	}

	query = &fakeTraceQuerier{row: fakeRow{record: record}}
	_, err = GetTraceRecord(context.Background(), query, "exec-1", "")
	if err != nil {
		t.Fatalf("GetTraceRecord() fallback error = %v", err)
	}
	if len(query.queryArgs) != 1 {
		t.Fatalf("fallback query args = %+v", query.queryArgs)
	}

	if _, err := GetTraceRecord(context.Background(), &fakeTraceQuerier{row: fakeRow{err: pgx.ErrNoRows}}, "exec-1", "step-1"); !errors.Is(err, pgx.ErrNoRows) {
		t.Fatalf("GetTraceRecord() error = %v", err)
	}
	if _, err := GetTraceRecord(context.Background(), &fakeTraceQuerier{row: fakeRow{err: errors.New("scan failed")}}, "exec-1", "step-1"); err == nil || err.Error() != "scan reasoning trace record: scan failed" {
		t.Fatalf("GetTraceRecord() wrapped error = %v", err)
	}
}
