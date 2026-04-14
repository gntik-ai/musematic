package persistence

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrNotFound      = errors.New("record not found")
	ErrAlreadyExists = errors.New("record already exists")
)

type SimulationRecord struct {
	SimulationID       string
	AgentImage         string
	AgentConfigJSON    []byte
	Status             string
	Namespace          string
	PodName            string
	CPURequest         string
	MemoryRequest      string
	MaxDurationSeconds int32
	CreatedAt          time.Time
	StartedAt          *time.Time
	CompletedAt        *time.Time
	TerminatedAt       *time.Time
	ErrorMessage       string
}

type SimulationStatusUpdate struct {
	Status       string
	PodName      string
	StartedAt    *time.Time
	CompletedAt  *time.Time
	TerminatedAt *time.Time
	ErrorMessage *string
}

type SimulationArtifactRecord struct {
	SimulationID string
	ObjectKey    string
	Filename     string
	SizeBytes    int64
	ContentType  string
}

type ATESessionRecord struct {
	SessionID       string
	SimulationID    string
	AgentID         string
	ScenariosJSON   []byte
	ReportObjectKey string
	CreatedAt       time.Time
	CompletedAt     *time.Time
}

type ATEResultRecord struct {
	SessionID       string
	ScenarioID      string
	Passed          bool
	QualityScore    *float64
	LatencyMS       *int32
	Cost            *float64
	SafetyCompliant *bool
	ErrorMessage    string
}

type storeDB interface {
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

type Store struct {
	db   storeDB
	pool *pgxpool.Pool
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

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := pool.Ping(ctx); err != nil {
		panic(err)
	}

	return pool
}

func NewStore(pool *pgxpool.Pool) *Store {
	return &Store{db: pool, pool: pool}
}

func (s *Store) Pool() *pgxpool.Pool {
	if s == nil {
		return nil
	}
	return s.pool
}

func (s *Store) InsertSimulation(ctx context.Context, record SimulationRecord) error {
	if s == nil || s.db == nil {
		return errors.New("postgres store is not configured")
	}

	_, err := s.db.Exec(
		ctx,
		`INSERT INTO simulations (
			simulation_id, agent_image, agent_config_json, status, namespace, pod_name,
			cpu_request, memory_request, max_duration_seconds, created_at, started_at,
			completed_at, terminated_at, error_message
		) VALUES ($1,$2,$3,$4,$5,NULLIF($6, ''),$7,$8,$9,$10,$11,$12,$13,NULLIF($14, ''))`,
		record.SimulationID,
		record.AgentImage,
		record.AgentConfigJSON,
		record.Status,
		record.Namespace,
		record.PodName,
		record.CPURequest,
		record.MemoryRequest,
		record.MaxDurationSeconds,
		record.CreatedAt,
		record.StartedAt,
		record.CompletedAt,
		record.TerminatedAt,
		record.ErrorMessage,
	)
	return mapPGError(err)
}

func (s *Store) UpdateSimulationStatus(ctx context.Context, simulationID string, update SimulationStatusUpdate) error {
	if s == nil || s.db == nil {
		return errors.New("postgres store is not configured")
	}

	tag, err := s.db.Exec(
		ctx,
		`UPDATE simulations
		SET status = $2,
		    pod_name = COALESCE(NULLIF($3, ''), pod_name),
		    started_at = COALESCE($4, started_at),
		    completed_at = COALESCE($5, completed_at),
		    terminated_at = COALESCE($6, terminated_at),
		    error_message = COALESCE($7, error_message)
		WHERE simulation_id = $1`,
		simulationID,
		update.Status,
		update.PodName,
		update.StartedAt,
		update.CompletedAt,
		update.TerminatedAt,
		update.ErrorMessage,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *Store) GetSimulation(ctx context.Context, simulationID string) (SimulationRecord, error) {
	if s == nil || s.db == nil {
		return SimulationRecord{}, errors.New("postgres store is not configured")
	}

	var record SimulationRecord
	err := s.db.QueryRow(
		ctx,
		`SELECT simulation_id, agent_image, agent_config_json, status, namespace, COALESCE(pod_name, ''),
		        cpu_request, memory_request, max_duration_seconds, created_at, started_at,
		        completed_at, terminated_at, COALESCE(error_message, '')
		 FROM simulations
		 WHERE simulation_id = $1`,
		simulationID,
	).Scan(
		&record.SimulationID,
		&record.AgentImage,
		&record.AgentConfigJSON,
		&record.Status,
		&record.Namespace,
		&record.PodName,
		&record.CPURequest,
		&record.MemoryRequest,
		&record.MaxDurationSeconds,
		&record.CreatedAt,
		&record.StartedAt,
		&record.CompletedAt,
		&record.TerminatedAt,
		&record.ErrorMessage,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return SimulationRecord{}, ErrNotFound
		}
		return SimulationRecord{}, err
	}
	return record, nil
}

func (s *Store) InsertSimulationArtifact(ctx context.Context, record SimulationArtifactRecord) error {
	if s == nil || s.db == nil {
		return errors.New("postgres store is not configured")
	}

	_, err := s.db.Exec(
		ctx,
		`INSERT INTO simulation_artifacts (simulation_id, object_key, filename, size_bytes, content_type)
		 VALUES ($1,$2,$3,$4,$5)`,
		record.SimulationID,
		record.ObjectKey,
		record.Filename,
		record.SizeBytes,
		record.ContentType,
	)
	return mapPGError(err)
}

func (s *Store) InsertATESession(ctx context.Context, record ATESessionRecord) error {
	if s == nil || s.db == nil {
		return errors.New("postgres store is not configured")
	}

	_, err := s.db.Exec(
		ctx,
		`INSERT INTO ate_sessions (session_id, simulation_id, agent_id, scenarios_json, report_object_key, created_at, completed_at)
		 VALUES ($1,$2,$3,$4,NULLIF($5, ''),$6,$7)`,
		record.SessionID,
		record.SimulationID,
		record.AgentID,
		record.ScenariosJSON,
		record.ReportObjectKey,
		record.CreatedAt,
		record.CompletedAt,
	)
	return mapPGError(err)
}

func (s *Store) InsertATEResult(ctx context.Context, record ATEResultRecord) error {
	if s == nil || s.db == nil {
		return errors.New("postgres store is not configured")
	}

	_, err := s.db.Exec(
		ctx,
		`INSERT INTO ate_results (
			session_id, scenario_id, passed, quality_score, latency_ms, cost, safety_compliant, error_message
		) VALUES ($1,$2,$3,$4,$5,$6,$7,NULLIF($8, ''))
		ON CONFLICT (session_id, scenario_id) DO UPDATE SET
			passed = EXCLUDED.passed,
			quality_score = EXCLUDED.quality_score,
			latency_ms = EXCLUDED.latency_ms,
			cost = EXCLUDED.cost,
			safety_compliant = EXCLUDED.safety_compliant,
			error_message = EXCLUDED.error_message`,
		record.SessionID,
		record.ScenarioID,
		record.Passed,
		record.QualityScore,
		record.LatencyMS,
		record.Cost,
		record.SafetyCompliant,
		record.ErrorMessage,
	)
	return mapPGError(err)
}

func (s *Store) UpdateATEReport(ctx context.Context, sessionID, objectKey string, completedAt time.Time) error {
	if s == nil || s.db == nil {
		return errors.New("postgres store is not configured")
	}

	tag, err := s.db.Exec(
		ctx,
		`UPDATE ate_sessions
		 SET report_object_key = $2, completed_at = $3
		 WHERE session_id = $1`,
		sessionID,
		objectKey,
		completedAt,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *Store) FindATESessionIDBySimulation(ctx context.Context, simulationID string) (string, error) {
	if s == nil || s.db == nil {
		return "", errors.New("postgres store is not configured")
	}

	var sessionID string
	err := s.db.QueryRow(
		ctx,
		`SELECT session_id FROM ate_sessions WHERE simulation_id = $1`,
		simulationID,
	).Scan(&sessionID)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return "", ErrNotFound
		}
		return "", err
	}
	return sessionID, nil
}

func mapPGError(err error) error {
	if err == nil {
		return nil
	}

	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "23505" {
		return ErrAlreadyExists
	}
	return err
}
