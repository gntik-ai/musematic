package sandbox

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/events"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	"github.com/google/uuid"
	"google.golang.org/protobuf/types/known/timestamppb"
)

func (m *Manager) Transition(ctx context.Context, sandboxID string, fromState sandboxv1.SandboxState, toState sandboxv1.SandboxState, reason string) error {
	m.mu.Lock()
	entry, ok := m.sandboxes[sandboxID]
	if !ok {
		m.mu.Unlock()
		return ErrSandboxNotFound
	}
	if fromState != sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED && entry.State != fromState {
		m.mu.Unlock()
		return fmt.Errorf("%w: expected %s got %s", ErrInvalidState, fromState.String(), entry.State.String())
	}
	if !validTransition(entry.State, toState) {
		m.mu.Unlock()
		return fmt.Errorf("%w: %s -> %s", ErrInvalidState, entry.State.String(), toState.String())
	}
	entry.State = toState
	entry.FailureReason = reason
	now := time.Now().UTC()
	if toState == sandboxv1.SandboxState_SANDBOX_STATE_READY {
		entry.ReadyAt = now
	}
	if toState == sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED {
		entry.TerminatedAt = now
	}
	entry.LastActivityAt = now
	total := entry.TotalDurationMS
	record := entry.Copy()
	m.mu.Unlock()

	if m.store != nil {
		if err := m.store.UpdateSandboxState(ctx, sandboxID, stateName(toState), reason, record.TotalSteps, &total); err != nil {
			return err
		}
	}
	return m.emitState(ctx, record, eventTypeForState(toState), eventNameForState(toState))
}

func (m *Manager) MarkFailed(ctx context.Context, sandboxID string, reason string) error {
	return m.Transition(ctx, sandboxID, sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED, sandboxv1.SandboxState_SANDBOX_STATE_FAILED, reason)
}

func (m *Manager) MarkTerminated(ctx context.Context, sandboxID string, gracePeriod int64) error {
	entry, err := m.Get(sandboxID)
	if err != nil {
		return err
	}
	if gracePeriod < 0 {
		gracePeriod = 0
	}
	if err := m.pods.DeletePod(ctx, entry.PodName, gracePeriod); err != nil {
		return err
	}
	waitCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	for {
		select {
		case <-waitCtx.Done():
			goto updateState
		default:
			if _, err := m.pods.GetPod(waitCtx, entry.PodName); err != nil {
				goto updateState
			}
			time.Sleep(100 * time.Millisecond)
		}
	}

updateState:
	_ = m.Transition(ctx, sandboxID, sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED, sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED, "")
	m.mu.Lock()
	delete(m.sandboxes, sandboxID)
	m.mu.Unlock()
	return nil
}

func (m *Manager) emitState(ctx context.Context, entry *Entry, eventType sandboxv1.SandboxEventType, name string) error {
	if entry == nil {
		return nil
	}
	details, err := json.Marshal(map[string]any{
		"sandbox_id": entry.SandboxID,
		"template":   entry.Template,
		"state":      stateName(entry.State),
	})
	if err != nil {
		return err
	}
	envelope := events.BuildEnvelope(name, entry.SandboxID, entry.ExecutionID, entry.Correlation, map[string]any{
		"sandbox_id": entry.SandboxID,
		"template":   entry.Template,
		"state":      stateName(entry.State),
	})
	event := &sandboxv1.SandboxEvent{
		EventId:     envelope.EventID,
		SandboxId:   entry.SandboxID,
		ExecutionId: entry.ExecutionID,
		EventType:   eventType,
		OccurredAt:  timestamppb.New(envelope.OccurredAt),
		DetailsJson: string(details),
		NewState:    entry.State,
	}
	if m.store != nil {
		payload, _ := json.Marshal(envelope)
		_ = m.store.InsertSandboxEvent(ctx, state.SandboxEventRecord{
			EventID:     uuid.MustParse(envelope.EventID),
			SandboxID:   uuid.MustParse(entry.SandboxID),
			ExecutionID: entry.ExecutionID,
			EventType:   name,
			Payload:     payload,
			EmittedAt:   envelope.OccurredAt,
		})
	}
	if m.emitter != nil {
		return m.emitter.Emit(ctx, event, envelope)
	}
	return nil
}

func validTransition(fromState sandboxv1.SandboxState, toState sandboxv1.SandboxState) bool {
	if fromState == toState {
		return true
	}
	switch fromState {
	case sandboxv1.SandboxState_SANDBOX_STATE_CREATING:
		return toState == sandboxv1.SandboxState_SANDBOX_STATE_READY || toState == sandboxv1.SandboxState_SANDBOX_STATE_FAILED
	case sandboxv1.SandboxState_SANDBOX_STATE_READY:
		return toState == sandboxv1.SandboxState_SANDBOX_STATE_EXECUTING || toState == sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED || toState == sandboxv1.SandboxState_SANDBOX_STATE_FAILED
	case sandboxv1.SandboxState_SANDBOX_STATE_EXECUTING:
		return toState == sandboxv1.SandboxState_SANDBOX_STATE_READY || toState == sandboxv1.SandboxState_SANDBOX_STATE_FAILED || toState == sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED
	case sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED:
		return toState == sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED
	case sandboxv1.SandboxState_SANDBOX_STATE_FAILED:
		return toState == sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED
	default:
		return toState == sandboxv1.SandboxState_SANDBOX_STATE_CREATING
	}
}

func eventTypeForState(stateValue sandboxv1.SandboxState) sandboxv1.SandboxEventType {
	switch stateValue {
	case sandboxv1.SandboxState_SANDBOX_STATE_READY:
		return sandboxv1.SandboxEventType_SANDBOX_EVENT_READY
	case sandboxv1.SandboxState_SANDBOX_STATE_FAILED:
		return sandboxv1.SandboxEventType_SANDBOX_EVENT_FAILED
	case sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED:
		return sandboxv1.SandboxEventType_SANDBOX_EVENT_COMPLETED
	case sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED:
		return sandboxv1.SandboxEventType_SANDBOX_EVENT_TERMINATED
	default:
		return sandboxv1.SandboxEventType_SANDBOX_EVENT_CREATED
	}
}

func eventNameForState(stateValue sandboxv1.SandboxState) string {
	switch stateValue {
	case sandboxv1.SandboxState_SANDBOX_STATE_READY:
		return "sandbox.ready"
	case sandboxv1.SandboxState_SANDBOX_STATE_FAILED:
		return "sandbox.failed"
	case sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED:
		return "sandbox.completed"
	case sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED:
		return "sandbox.terminated"
	default:
		return "sandbox.created"
	}
}
