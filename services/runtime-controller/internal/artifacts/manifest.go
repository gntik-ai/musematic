package artifacts

import (
	"encoding/json"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
)

func BuildManifest(runtimeID string, executionID string, entries []*runtimev1.ArtifactEntry, complete bool) (*runtimev1.RuntimeEvent, error) {
	details, err := json.Marshal(map[string]any{
		"complete":  complete,
		"artifacts": entries,
	})
	if err != nil {
		return nil, err
	}
	envelope := events.BuildEnvelope("runtime.artifacts.collected", runtimeID, executionID, &runtimev1.CorrelationContext{
		ExecutionId: executionID,
	}, map[string]any{"complete": complete})
	return events.RuntimeEventFromEnvelope(envelope, runtimev1.RuntimeEventType_RUNTIME_EVENT_ARTIFACT_COLLECTED, runtimev1.RuntimeState_RUNTIME_STATE_RUNNING, string(details)), nil
}
