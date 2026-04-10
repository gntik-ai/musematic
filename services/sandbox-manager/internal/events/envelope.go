package events

import (
	"encoding/json"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/google/uuid"
)

type Envelope struct {
	EventID            string                        `json:"event_id"`
	EventType          string                        `json:"event_type"`
	Source             string                        `json:"source"`
	SandboxID          string                        `json:"sandbox_id,omitempty"`
	ExecutionID        string                        `json:"execution_id,omitempty"`
	OccurredAt         time.Time                     `json:"occurred_at"`
	TraceID            string                        `json:"trace_id,omitempty"`
	CorrelationContext *sandboxv1.CorrelationContext `json:"correlation_context,omitempty"`
	Payload            any                           `json:"payload,omitempty"`
}

func BuildEnvelope(eventType string, sandboxID string, executionID string, correlation *sandboxv1.CorrelationContext, payload any) Envelope {
	traceID := ""
	if correlation != nil {
		traceID = correlation.TraceId
	}
	return Envelope{
		EventID:            uuid.NewString(),
		EventType:          eventType,
		Source:             "sandbox-manager",
		SandboxID:          sandboxID,
		ExecutionID:        executionID,
		OccurredAt:         time.Now().UTC(),
		TraceID:            traceID,
		CorrelationContext: correlation,
		Payload:            payload,
	}
}

func (e Envelope) MarshalJSON() ([]byte, error) {
	return json.Marshal(struct {
		EventID            string                        `json:"event_id"`
		EventType          string                        `json:"event_type"`
		Source             string                        `json:"source"`
		SandboxID          string                        `json:"sandbox_id,omitempty"`
		ExecutionID        string                        `json:"execution_id,omitempty"`
		OccurredAt         string                        `json:"occurred_at"`
		TraceID            string                        `json:"trace_id,omitempty"`
		CorrelationContext *sandboxv1.CorrelationContext `json:"correlation_context,omitempty"`
		Payload            any                           `json:"payload,omitempty"`
	}{
		EventID:            e.EventID,
		EventType:          e.EventType,
		Source:             e.Source,
		SandboxID:          e.SandboxID,
		ExecutionID:        e.ExecutionID,
		OccurredAt:         e.OccurredAt.Format(time.RFC3339Nano),
		TraceID:            e.TraceID,
		CorrelationContext: e.CorrelationContext,
		Payload:            e.Payload,
	})
}
