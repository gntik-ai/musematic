package state

import (
	"context"
	"encoding/json"
	"fmt"
	"path"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

func (s *Store) InsertRuntime(ctx context.Context, record RuntimeRecord) error {
	if record.RuntimeID == uuid.Nil {
		record.RuntimeID = uuid.New()
	}
	_, err := s.pool.Exec(ctx, `
INSERT INTO runtimes (
    runtime_id, execution_id, step_id, workspace_id, agent_fqn, agent_revision,
    model_binding, state, failure_reason, pod_name, pod_namespace, correlation_context,
    resource_limits, secret_refs, launched_at, stopped_at, last_heartbeat_at
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,COALESCE($11,'platform-execution'),$12,$13,$14,$15,$16,$17)`,
		record.RuntimeID, record.ExecutionID, nilIfEmpty(record.StepID), record.WorkspaceID, record.AgentFQN,
		record.AgentRevision, json.RawMessage(record.ModelBinding), record.State, nilIfEmpty(record.FailureReason),
		nilIfEmpty(record.PodName), nilIfEmpty(record.PodNamespace), json.RawMessage(record.CorrelationContext),
		json.RawMessage(record.ResourceLimits), record.SecretRefs, record.LaunchedAt, record.StoppedAt, record.LastHeartbeatAt,
	)
	return err
}

func (s *Store) GetRuntimeByExecutionID(ctx context.Context, executionID string) (RuntimeRecord, error) {
	row := s.pool.QueryRow(ctx, `
SELECT runtime_id, execution_id, COALESCE(step_id,''), workspace_id, agent_fqn, agent_revision,
       model_binding, state, COALESCE(failure_reason,''), COALESCE(pod_name,''), pod_namespace,
       correlation_context, resource_limits, COALESCE(secret_refs,'{}'::text[]),
       launched_at, stopped_at, last_heartbeat_at, created_at, updated_at
FROM runtimes WHERE execution_id=$1`, executionID)
	return scanRuntime(row)
}

func (s *Store) UpdateRuntimeState(ctx context.Context, executionID string, state string, reason string) error {
	_, err := s.pool.Exec(ctx, `
UPDATE runtimes
SET state=$2, failure_reason=NULLIF($3,''), updated_at=NOW(),
    launched_at = CASE WHEN $2='running' AND launched_at IS NULL THEN NOW() ELSE launched_at END,
    stopped_at = CASE WHEN $2 IN ('stopped','force_stopped','failed') THEN NOW() ELSE stopped_at END
WHERE execution_id=$1`, executionID, state, reason)
	return err
}

func (s *Store) UpdateLastHeartbeat(ctx context.Context, executionID string, at time.Time) error {
	_, err := s.pool.Exec(ctx, `
UPDATE runtimes
SET last_heartbeat_at=$2, updated_at=NOW()
WHERE execution_id=$1`, executionID, at)
	return err
}

func (s *Store) ListActiveRuntimes(ctx context.Context) ([]RuntimeRecord, error) {
	rows, err := s.pool.Query(ctx, `
SELECT runtime_id, execution_id, COALESCE(step_id,''), workspace_id, agent_fqn, agent_revision,
       model_binding, state, COALESCE(failure_reason,''), COALESCE(pod_name,''), pod_namespace,
       correlation_context, resource_limits, COALESCE(secret_refs,'{}'::text[]),
       launched_at, stopped_at, last_heartbeat_at, created_at, updated_at
FROM runtimes WHERE state IN ('pending','running','paused')`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []RuntimeRecord
	for rows.Next() {
		record, err := scanRuntime(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, record)
	}
	return out, rows.Err()
}

func (s *Store) InsertWarmPoolPod(ctx context.Context, pod WarmPoolPod) error {
	if pod.PodID == uuid.Nil {
		pod.PodID = uuid.New()
	}
	_, err := s.pool.Exec(ctx, `
INSERT INTO warm_pool_pods (
    pod_id, workspace_id, agent_type, pod_name, pod_namespace, status,
    dispatched_to, ready_at, idle_since, dispatched_at
) VALUES ($1,$2,$3,$4,COALESCE($5,'platform-execution'),$6,$7,$8,$9,$10)
ON CONFLICT (pod_name) DO UPDATE
SET status=EXCLUDED.status, dispatched_to=EXCLUDED.dispatched_to, ready_at=EXCLUDED.ready_at,
    idle_since=EXCLUDED.idle_since, dispatched_at=EXCLUDED.dispatched_at`,
		pod.PodID, pod.WorkspaceID, pod.AgentType, pod.PodName, nilIfEmpty(pod.PodNamespace), pod.Status,
		pod.DispatchedTo, pod.ReadyAt, pod.IdleSince, pod.DispatchedAt,
	)
	return err
}

func (s *Store) GetReadyWarmPod(ctx context.Context, workspaceID string, agentType string) (WarmPoolPod, error) {
	row := s.pool.QueryRow(ctx, `
SELECT pod_id, workspace_id, agent_type, pod_name, pod_namespace, status,
       dispatched_to, created_at, ready_at, idle_since, dispatched_at
FROM warm_pool_pods
WHERE workspace_id=$1 AND agent_type=$2 AND status='ready'
ORDER BY ready_at NULLS LAST, created_at
LIMIT 1`, workspaceID, agentType)
	var pod WarmPoolPod
	err := row.Scan(&pod.PodID, &pod.WorkspaceID, &pod.AgentType, &pod.PodName, &pod.PodNamespace,
		&pod.Status, &pod.DispatchedTo, &pod.CreatedAt, &pod.ReadyAt, &pod.IdleSince, &pod.DispatchedAt)
	return pod, err
}

func (s *Store) UpdateWarmPoolPodStatus(ctx context.Context, podName string, status string, runtimeID *uuid.UUID) error {
	_, err := s.pool.Exec(ctx, `
UPDATE warm_pool_pods
SET status=$2, dispatched_to=$3,
    ready_at = CASE WHEN $2='ready' THEN NOW() ELSE ready_at END,
    idle_since = CASE WHEN $2='ready' THEN NOW() ELSE idle_since END,
    dispatched_at = CASE WHEN $2='dispatched' THEN NOW() ELSE dispatched_at END
WHERE pod_name=$1`, podName, status, runtimeID)
	return err
}

func (s *Store) ListWarmPoolPodsByStatus(ctx context.Context, status string) ([]WarmPoolPod, error) {
	rows, err := s.pool.Query(ctx, `
SELECT pod_id, workspace_id, agent_type, pod_name, pod_namespace, status,
       dispatched_to, created_at, ready_at, idle_since, dispatched_at
FROM warm_pool_pods WHERE status=$1`, status)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var pods []WarmPoolPod
	for rows.Next() {
		var pod WarmPoolPod
		if err := rows.Scan(&pod.PodID, &pod.WorkspaceID, &pod.AgentType, &pod.PodName, &pod.PodNamespace,
			&pod.Status, &pod.DispatchedTo, &pod.CreatedAt, &pod.ReadyAt, &pod.IdleSince, &pod.DispatchedAt); err != nil {
			return nil, err
		}
		pods = append(pods, pod)
	}
	return pods, rows.Err()
}

func (s *Store) InsertTaskPlanRecord(ctx context.Context, record TaskPlanRecord) error {
	if record.RecordID == uuid.Nil {
		record.RecordID = uuid.New()
	}
	prepared, err := s.prepareTaskPlanRecord(ctx, record)
	if err != nil {
		return err
	}
	_, err = s.pool.Exec(ctx, `
INSERT INTO task_plan_records (
    record_id, execution_id, step_id, workspace_id, considered_agents, selected_agent,
    selection_rationale, parameters, parameter_provenance, payload_json, payload_object_key
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
		prepared.RecordID, prepared.ExecutionID, nilIfEmpty(prepared.StepID), prepared.WorkspaceID,
		nullJSON(prepared.ConsideredAgents), nilIfEmpty(prepared.SelectedAgent), nilIfEmpty(prepared.SelectionRationale),
		nullJSON(prepared.Parameters), nullJSON(prepared.ParameterProvenance), nullJSON(prepared.PayloadJSON), nilIfEmpty(prepared.PayloadObjectKey),
	)
	return err
}

func (s *Store) prepareTaskPlanRecord(ctx context.Context, record TaskPlanRecord) (TaskPlanRecord, error) {
	if len(record.PayloadJSON) <= 65536 {
		return record, nil
	}
	if s.TaskPlanUploader == nil {
		return TaskPlanRecord{}, fmt.Errorf("task plan payload exceeds 65536 bytes and no uploader is configured")
	}
	stepID := record.StepID
	if stepID == "" {
		stepID = "task-plan"
	}
	key := path.Join("task-plans", record.ExecutionID, stepID+".json")
	if err := s.TaskPlanUploader.UploadTaskPlan(ctx, key, []byte(record.PayloadJSON)); err != nil {
		return TaskPlanRecord{}, err
	}
	record.PayloadJSON = nil
	record.PayloadObjectKey = key
	return record, nil
}

func (s *Store) InsertRuntimeEvent(ctx context.Context, event RuntimeEventRecord) error {
	if event.EventID == uuid.Nil {
		event.EventID = uuid.New()
	}
	_, err := s.pool.Exec(ctx, `
INSERT INTO runtime_events (event_id, runtime_id, execution_id, event_type, payload, emitted_at)
VALUES ($1,$2,$3,$4,$5,COALESCE($6,NOW()))`,
		event.EventID, event.RuntimeID, event.ExecutionID, event.EventType, json.RawMessage(event.Payload), zeroTimeToNil(event.EmittedAt),
	)
	return err
}

func (s *Store) GetRuntimeEventsSince(ctx context.Context, executionID string, since time.Time) ([]RuntimeEventRecord, error) {
	rows, err := s.pool.Query(ctx, `
SELECT event_id, runtime_id, execution_id, event_type, payload, emitted_at
FROM runtime_events
WHERE execution_id=$1 AND emitted_at >= $2
ORDER BY emitted_at ASC`, executionID, since)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var events []RuntimeEventRecord
	for rows.Next() {
		var event RuntimeEventRecord
		if err := rows.Scan(&event.EventID, &event.RuntimeID, &event.ExecutionID, &event.EventType, &event.Payload, &event.EmittedAt); err != nil {
			return nil, err
		}
		events = append(events, event)
	}
	return events, rows.Err()
}

type scanner interface {
	Scan(dest ...any) error
}

func scanRuntime(row scanner) (RuntimeRecord, error) {
	var record RuntimeRecord
	err := row.Scan(
		&record.RuntimeID,
		&record.ExecutionID,
		&record.StepID,
		&record.WorkspaceID,
		&record.AgentFQN,
		&record.AgentRevision,
		&record.ModelBinding,
		&record.State,
		&record.FailureReason,
		&record.PodName,
		&record.PodNamespace,
		&record.CorrelationContext,
		&record.ResourceLimits,
		&record.SecretRefs,
		&record.LaunchedAt,
		&record.StoppedAt,
		&record.LastHeartbeatAt,
		&record.CreatedAt,
		&record.UpdatedAt,
	)
	return record, err
}

func nilIfEmpty(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func nullJSON(value json.RawMessage) any {
	if len(value) == 0 {
		return nil
	}
	return value
}

func zeroTimeToNil(value time.Time) any {
	if value.IsZero() {
		return nil
	}
	return value
}

func IsNotFound(err error) bool {
	return err == pgx.ErrNoRows
}
