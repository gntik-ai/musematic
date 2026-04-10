package reconciler

import (
	"context"
	"encoding/json"
	"log/slog"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
)

type EventRecorder interface {
	InsertRuntimeEvent(context.Context, state.RuntimeEventRecord) error
}

func ApplyRepairs(ctx context.Context, report DriftReport, store RuntimeLister, pods PodLister, recorder EventRecorder, emitter *events.EventEmitter, fanout *events.FanoutRegistry, logger *slog.Logger) error {
	for _, orphan := range report.Orphans {
		if err := pods.DeletePod(ctx, orphan.Name, 0); err != nil && logger != nil {
			logger.Error("delete orphan pod", "pod", orphan.Name, "error", err)
		}
	}
	for _, missing := range report.Missing {
		if err := store.UpdateRuntimeState(ctx, missing.Runtime.ExecutionID, "failed", "pod_disappeared"); err != nil {
			return err
		}
		publishRepairEvent(ctx, missing.Runtime, "runtime.drift.missing", runtimev1.RuntimeEventType_RUNTIME_EVENT_DRIFT_DETECTED, runtimev1.RuntimeState_RUNTIME_STATE_FAILED, recorder, emitter, fanout)
	}
	for _, mismatch := range report.Mismatches {
		if err := store.UpdateRuntimeState(ctx, mismatch.Runtime.ExecutionID, mismatch.Reason, ""); err != nil {
			return err
		}
		eventType := runtimev1.RuntimeEventType_RUNTIME_EVENT_DRIFT_DETECTED
		stateValue := runtimev1.RuntimeState_RUNTIME_STATE_RUNNING
		if mismatch.Reason == "failed" {
			stateValue = runtimev1.RuntimeState_RUNTIME_STATE_FAILED
		}
		publishRepairEvent(ctx, mismatch.Runtime, "runtime.drift.mismatch", eventType, stateValue, recorder, emitter, fanout)
	}
	return nil
}

func publishRepairEvent(ctx context.Context, runtime state.RuntimeRecord, name string, eventType runtimev1.RuntimeEventType, newState runtimev1.RuntimeState, recorder EventRecorder, emitter *events.EventEmitter, fanout *events.FanoutRegistry) {
	envelope := events.BuildEnvelope(name, runtime.RuntimeID.String(), runtime.ExecutionID, &runtimev1.CorrelationContext{
		WorkspaceId: runtime.WorkspaceID,
		ExecutionId: runtime.ExecutionID,
	}, map[string]string{"reason": name})
	event := events.RuntimeEventFromEnvelope(envelope, eventType, newState, name)
	if recorder != nil {
		_ = recorder.InsertRuntimeEvent(ctx, state.RuntimeEventRecord{
			RuntimeID:   runtime.RuntimeID,
			ExecutionID: runtime.ExecutionID,
			EventType:   name,
			Payload:     mustRepairJSON(event),
		})
	}
	if emitter != nil {
		_ = emitter.EmitDrift(ctx, event, envelope)
	}
	if fanout != nil {
		fanout.Publish(event)
	}
}

func mustRepairJSON(value any) json.RawMessage {
	body, _ := json.Marshal(value)
	return body
}
