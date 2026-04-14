package state

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
)

func (s *Store) InsertSandbox(ctx context.Context, record SandboxRecord) error {
	_, err := s.db.Exec(ctx, `
INSERT INTO sandboxes (
    sandbox_id, execution_id, workspace_id, template, state, failure_reason,
    pod_name, pod_namespace, resource_limits, network_enabled, total_steps,
    total_duration_ms, created_at, ready_at, terminated_at, updated_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,COALESCE($13, NOW()),$14,$15,COALESCE($16, NOW()))
`, record.SandboxID, record.ExecutionID, record.WorkspaceID, record.Template, record.State, record.FailureReason,
		record.PodName, record.PodNamespace, record.ResourceLimits, record.NetworkEnabled, record.TotalSteps,
		record.TotalDurationMS, nullableTime(record.CreatedAt), record.ReadyAt, record.TerminatedAt, nullableTime(record.UpdatedAt))
	return err
}

func (s *Store) UpdateSandboxState(ctx context.Context, sandboxID string, stateValue string, reason string, totalSteps int32, totalDurationMS *int64) error {
	_, err := s.db.Exec(ctx, `
UPDATE sandboxes
SET state = $2,
    failure_reason = NULLIF($3, ''),
    total_steps = $4,
    total_duration_ms = $5,
    ready_at = CASE WHEN $2 = 'ready' THEN NOW() ELSE ready_at END,
    terminated_at = CASE WHEN $2 = 'terminated' THEN NOW() ELSE terminated_at END,
    updated_at = NOW()
WHERE sandbox_id = $1
`, sandboxID, stateValue, reason, totalSteps, totalDurationMS)
	return err
}

func (s *Store) GetSandbox(ctx context.Context, sandboxID string) (SandboxRecord, error) {
	row := s.db.QueryRow(ctx, `
SELECT sandbox_id, execution_id, workspace_id, template, state, COALESCE(failure_reason, ''),
       COALESCE(pod_name, ''), pod_namespace, resource_limits, network_enabled,
       total_steps, total_duration_ms, created_at, ready_at, terminated_at, updated_at
FROM sandboxes
WHERE sandbox_id = $1
`, sandboxID)
	var record SandboxRecord
	err := row.Scan(
		&record.SandboxID,
		&record.ExecutionID,
		&record.WorkspaceID,
		&record.Template,
		&record.State,
		&record.FailureReason,
		&record.PodName,
		&record.PodNamespace,
		&record.ResourceLimits,
		&record.NetworkEnabled,
		&record.TotalSteps,
		&record.TotalDurationMS,
		&record.CreatedAt,
		&record.ReadyAt,
		&record.TerminatedAt,
		&record.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			return SandboxRecord{}, ErrNotFound
		}
		if errors.Is(err, pgx.ErrNoRows) || err.Error() == "no rows in result set" {
			return SandboxRecord{}, ErrNotFound
		}
		return SandboxRecord{}, err
	}
	return record, nil
}

func (s *Store) InsertSandboxEvent(ctx context.Context, record SandboxEventRecord) error {
	_, err := s.db.Exec(ctx, `
INSERT INTO sandbox_events (event_id, sandbox_id, execution_id, event_type, payload, emitted_at)
VALUES ($1,$2,$3,$4,$5,COALESCE($6, NOW()))
`, record.EventID, record.SandboxID, record.ExecutionID, record.EventType, record.Payload, nullableTime(record.EmittedAt))
	return err
}

func (s *Store) GetSandboxEventsSince(ctx context.Context, sandboxID string, since time.Time) ([]SandboxEventRecord, error) {
	rows, err := s.db.Query(ctx, `
SELECT event_id, sandbox_id, execution_id, event_type, payload, emitted_at
FROM sandbox_events
WHERE sandbox_id = $1 AND emitted_at >= $2
ORDER BY emitted_at ASC
`, sandboxID, since)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []SandboxEventRecord
	for rows.Next() {
		var record SandboxEventRecord
		if err := rows.Scan(&record.EventID, &record.SandboxID, &record.ExecutionID, &record.EventType, &record.Payload, &record.EmittedAt); err != nil {
			return nil, err
		}
		events = append(events, record)
	}
	return events, rows.Err()
}

func MarshalResourceLimits(resourceLimits any) json.RawMessage {
	if resourceLimits == nil {
		return json.RawMessage(`{}`)
	}
	body, err := json.Marshal(resourceLimits)
	if err != nil {
		return json.RawMessage(`{}`)
	}
	return body
}

func nullableTime(value time.Time) *time.Time {
	if value.IsZero() {
		return nil
	}
	return &value
}
