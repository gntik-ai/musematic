package state

import (
	"context"
	"encoding/json"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Store struct {
	pool             *pgxpool.Pool
	TaskPlanUploader TaskPlanUploader
}

type TaskPlanUploader interface {
	UploadTaskPlan(context.Context, string, []byte) error
}

type RuntimeRecord struct {
	RuntimeID          uuid.UUID
	ExecutionID        string
	StepID             string
	WorkspaceID        string
	AgentFQN           string
	AgentRevision      string
	ModelBinding       json.RawMessage
	State              string
	FailureReason      string
	PodName            string
	PodNamespace       string
	CorrelationContext json.RawMessage
	ResourceLimits     json.RawMessage
	SecretRefs         []string
	LaunchedAt         *time.Time
	StoppedAt          *time.Time
	LastHeartbeatAt    *time.Time
	CreatedAt          time.Time
	UpdatedAt          time.Time
}

type WarmPoolPod struct {
	PodID        uuid.UUID
	WorkspaceID  string
	AgentType    string
	PodName      string
	PodNamespace string
	Status       string
	DispatchedTo *uuid.UUID
	CreatedAt    time.Time
	ReadyAt      *time.Time
	IdleSince    *time.Time
	DispatchedAt *time.Time
}

type TaskPlanRecord struct {
	RecordID            uuid.UUID
	ExecutionID         string
	StepID              string
	WorkspaceID         string
	ConsideredAgents    json.RawMessage
	SelectedAgent       string
	SelectionRationale  string
	Parameters          json.RawMessage
	ParameterProvenance json.RawMessage
	PayloadJSON         json.RawMessage
	PayloadObjectKey    string
	PersistedAt         time.Time
}

type RuntimeEventRecord struct {
	EventID     uuid.UUID
	RuntimeID   uuid.UUID
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
	return &Store{pool: pool}, nil
}

func (s *Store) Pool() *pgxpool.Pool {
	return s.pool
}

func (s *Store) Close() {
	if s.pool != nil {
		s.pool.Close()
	}
}
