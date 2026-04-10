package events

import (
	"encoding/json"
	"testing"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
)

func TestBuildEnvelopeAndMarshalJSON(t *testing.T) {
	ctx := &runtimev1.CorrelationContext{ExecutionId: "exec-1", TraceId: "trace-1"}
	envelope := BuildEnvelope("runtime.launched", "rt-1", "exec-1", ctx, map[string]string{"state": "running"})

	if envelope.TraceID != "trace-1" || envelope.EventID == "" {
		t.Fatalf("unexpected envelope: %+v", envelope)
	}
	body, err := envelope.MarshalJSON()
	if err != nil {
		t.Fatalf("MarshalJSON returned error: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(body, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if decoded["event_type"] != "runtime.launched" || decoded["execution_id"] != "exec-1" {
		t.Fatalf("unexpected decoded envelope: %+v", decoded)
	}
}

func TestRuntimeEventFromEnvelope(t *testing.T) {
	event := RuntimeEventFromEnvelope(
		BuildEnvelope("runtime.failed", "rt-1", "exec-1", nil, nil),
		runtimev1.RuntimeEventType_RUNTIME_EVENT_FAILED,
		runtimev1.RuntimeState_RUNTIME_STATE_FAILED,
		"boom",
	)

	if event.EventId == "" || event.DetailsJson != "boom" || event.NewState != runtimev1.RuntimeState_RUNTIME_STATE_FAILED {
		t.Fatalf("unexpected runtime event: %+v", event)
	}
}
