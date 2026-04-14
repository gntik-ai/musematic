package events

import (
	"encoding/json"
	"testing"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
)

func TestBuildEnvelopeUsesCorrelationTraceID(t *testing.T) {
	t.Parallel()

	envelope := BuildEnvelope("sandbox.created", "sandbox-1", "exec-1", &sandboxv1.CorrelationContext{
		WorkspaceId: "ws-1",
		ExecutionId: "exec-1",
		TraceId:     "trace-1",
	}, map[string]string{"state": "creating"})
	if envelope.EventID == "" || envelope.Source != "sandbox-manager" {
		t.Fatalf("unexpected envelope %+v", envelope)
	}
	if envelope.TraceID != "trace-1" {
		t.Fatalf("expected trace id, got %q", envelope.TraceID)
	}
	if envelope.OccurredAt.Location() != time.UTC {
		t.Fatalf("expected UTC timestamp, got %s", envelope.OccurredAt.Location())
	}
}

func TestEnvelopeMarshalJSONFormatsTimestamp(t *testing.T) {
	t.Parallel()

	envelope := Envelope{
		EventID:     "event-1",
		EventType:   "sandbox.ready",
		Source:      "sandbox-manager",
		SandboxID:   "sandbox-1",
		ExecutionID: "exec-1",
		OccurredAt:  time.Date(2026, 4, 14, 12, 0, 0, 0, time.UTC),
		TraceID:     "trace-1",
		Payload:     map[string]string{"state": "ready"},
	}
	body, err := envelope.MarshalJSON()
	if err != nil {
		t.Fatalf("MarshalJSON() error = %v", err)
	}

	var decoded map[string]any
	if err := json.Unmarshal(body, &decoded); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	if decoded["occurred_at"] != "2026-04-14T12:00:00Z" {
		t.Fatalf("unexpected occurred_at %v", decoded["occurred_at"])
	}
}
