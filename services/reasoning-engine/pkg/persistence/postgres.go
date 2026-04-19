package persistence

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

type ReasoningTraceRecord struct {
	ExecutionID            string
	StepID                 string
	Technique              string
	StorageKey             string
	StepCount              int
	Status                 string
	ComputeBudgetUsed      float64
	ConsensusReached       *bool
	Stabilized             *bool
	DegradationDetected    *bool
	ComputeBudgetExhausted bool
	EffectiveBudgetScope   string
	CreatedAt              time.Time
	UpdatedAt              time.Time
}

type traceRecordQuerier interface {
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

type TraceRecordStore interface {
	InsertTraceRecord(ctx context.Context, record ReasoningTraceRecord) error
	GetTraceRecord(ctx context.Context, executionID, stepID string) (*ReasoningTraceRecord, error)
}

type PostgresTraceStore struct {
	db traceRecordQuerier
}

func NewPostgresPool(dsn string) *pgxpool.Pool {
	if dsn == "" {
		return nil
	}

	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		panic(err)
	}
	cfg.MaxConns = 20
	cfg.MinConns = 2

	pool, err := pgxpool.NewWithConfig(context.Background(), cfg)
	if err != nil {
		panic(err)
	}
	return pool
}

func NewTraceRecordStore(pool *pgxpool.Pool) *PostgresTraceStore {
	if pool == nil {
		return nil
	}
	return &PostgresTraceStore{db: pool}
}

func (s *PostgresTraceStore) InsertTraceRecord(ctx context.Context, record ReasoningTraceRecord) error {
	if s == nil || s.db == nil {
		return nil
	}
	return InsertTraceRecord(ctx, s.db, record)
}

func (s *PostgresTraceStore) GetTraceRecord(
	ctx context.Context,
	executionID string,
	stepID string,
) (*ReasoningTraceRecord, error) {
	if s == nil || s.db == nil {
		return nil, pgx.ErrNoRows
	}
	return GetTraceRecord(ctx, s.db, executionID, stepID)
}

func InsertTraceRecord(ctx context.Context, db traceRecordQuerier, record ReasoningTraceRecord) error {
	if db == nil {
		return nil
	}
	status := record.Status
	if status == "" {
		status = "complete"
	}
	var stepID any
	if record.StepID != "" {
		stepID = record.StepID
	}
	_, err := db.Exec(
		ctx,
		`INSERT INTO execution_reasoning_trace_records (
			execution_id,
			step_id,
			technique,
			storage_key,
			step_count,
			status,
			compute_budget_used,
			consensus_reached,
			stabilized,
			degradation_detected,
			compute_budget_exhausted,
			effective_budget_scope
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
		ON CONFLICT (execution_id, step_id) DO UPDATE SET
			technique = EXCLUDED.technique,
			storage_key = EXCLUDED.storage_key,
			step_count = EXCLUDED.step_count,
			status = EXCLUDED.status,
			compute_budget_used = EXCLUDED.compute_budget_used,
			consensus_reached = EXCLUDED.consensus_reached,
			stabilized = EXCLUDED.stabilized,
			degradation_detected = EXCLUDED.degradation_detected,
			compute_budget_exhausted = EXCLUDED.compute_budget_exhausted,
			effective_budget_scope = EXCLUDED.effective_budget_scope,
			updated_at = NOW()`,
		record.ExecutionID,
		stepID,
		record.Technique,
		record.StorageKey,
		record.StepCount,
		status,
		record.ComputeBudgetUsed,
		record.ConsensusReached,
		record.Stabilized,
		record.DegradationDetected,
		record.ComputeBudgetExhausted,
		nullIfEmpty(record.EffectiveBudgetScope),
	)
	return err
}

func GetTraceRecord(
	ctx context.Context,
	db traceRecordQuerier,
	executionID string,
	stepID string,
) (*ReasoningTraceRecord, error) {
	if db == nil {
		return nil, pgx.ErrNoRows
	}
	var query string
	var args []any
	if stepID != "" {
		query = `SELECT execution_id, COALESCE(step_id, ''), technique, storage_key, COALESCE(step_count, 0),
			status, COALESCE(compute_budget_used, 0), consensus_reached, stabilized,
			degradation_detected, COALESCE(compute_budget_exhausted, false), COALESCE(effective_budget_scope, ''), created_at, updated_at
			FROM execution_reasoning_trace_records
			WHERE execution_id = $1 AND step_id = $2`
		args = []any{executionID, stepID}
	} else {
		query = `SELECT execution_id, COALESCE(step_id, ''), technique, storage_key, COALESCE(step_count, 0),
			status, COALESCE(compute_budget_used, 0), consensus_reached, stabilized,
			degradation_detected, COALESCE(compute_budget_exhausted, false), COALESCE(effective_budget_scope, ''), created_at, updated_at
			FROM execution_reasoning_trace_records
			WHERE execution_id = $1
			ORDER BY created_at ASC, id ASC
			LIMIT 1`
		args = []any{executionID}
	}
	row := db.QueryRow(ctx, query, args...)
	record := &ReasoningTraceRecord{}
	var consensus *bool
	var stabilized *bool
	var degraded *bool
	if err := row.Scan(
		&record.ExecutionID,
		&record.StepID,
		&record.Technique,
		&record.StorageKey,
		&record.StepCount,
		&record.Status,
		&record.ComputeBudgetUsed,
		&consensus,
		&stabilized,
		&degraded,
		&record.ComputeBudgetExhausted,
		&record.EffectiveBudgetScope,
		&record.CreatedAt,
		&record.UpdatedAt,
	); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, err
		}
		return nil, fmt.Errorf("scan reasoning trace record: %w", err)
	}
	record.ConsensusReached = consensus
	record.Stabilized = stabilized
	record.DegradationDetected = degraded
	return record, nil
}

func nullIfEmpty(value string) any {
	if value == "" {
		return nil
	}
	return value
}
