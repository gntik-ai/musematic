package state

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrNotFound = errors.New("record not found")

type Store struct {
	pool *pgxpool.Pool
	db   queryExecutor
}

type queryExecutor interface {
	Exec(context.Context, string, ...any) (pgconn.CommandTag, error)
	Query(context.Context, string, ...any) (pgx.Rows, error)
	QueryRow(context.Context, string, ...any) pgx.Row
	Ping(context.Context) error
	Close()
}

type SandboxRecord struct {
	SandboxID       uuid.UUID
	ExecutionID     string
	WorkspaceID     string
	Template        string
	State           string
	FailureReason   string
	PodName         string
	PodNamespace    string
	ResourceLimits  json.RawMessage
	NetworkEnabled  bool
	TotalSteps      int32
	TotalDurationMS *int64
	CreatedAt       time.Time
	ReadyAt         *time.Time
	TerminatedAt    *time.Time
	UpdatedAt       time.Time
}

type SandboxEventRecord struct {
	EventID     uuid.UUID
	SandboxID   uuid.UUID
	ExecutionID string
	EventType   string
	Payload     json.RawMessage
	EmittedAt   time.Time
}

func NewStore(ctx context.Context, dsn string) (*Store, error) {
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		return nil, err
	}
	return &Store{pool: pool, db: pool}, nil
}

func newStoreForQueries(db queryExecutor) *Store {
	return &Store{db: db}
}

func (s *Store) Pool() *pgxpool.Pool {
	return s.pool
}

func (s *Store) Close() {
	if s.pool != nil {
		s.pool.Close()
		return
	}
	if s.db != nil {
		s.db.Close()
	}
}
