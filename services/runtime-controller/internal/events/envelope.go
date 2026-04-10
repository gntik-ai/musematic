package events

import (
	"encoding/json"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/google/uuid"
	"google.golang.org/protobuf/types/known/timestamppb"
)

type Envelope struct {
	EventID            string                        `json:"event_id"`
	EventType          string                        `json:"event_type"`
	RuntimeID          string                        `json:"runtime_id,omitempty"`
	ExecutionID        string                        `json:"execution_id,omitempty"`
	OccurredAt         time.Time                     `json:"occurred_at"`
	TraceID            string                        `json:"trace_id,omitempty"`
	CorrelationContext *runtimev1.CorrelationContext `json:"correlation_context,omitempty"`
	Payload            any                           `json:"payload,omitempty"`
}

func BuildEnvelope(eventType string, runtimeID string, executionID string, ctx *runtimev1.CorrelationContext, payload any) Envelope {
	traceID := ""
	if ctx != nil {
		traceID = ctx.TraceId
	}
	return Envelope{
		EventID:            uuid.NewString(),
		EventType:          eventType,
		RuntimeID:          runtimeID,
		ExecutionID:        executionID,
		OccurredAt:         time.Now().UTC(),
		TraceID:            traceID,
		CorrelationContext: ctx,
		Payload:            payload,
	}
}

func (e Envelope) MarshalJSON() ([]byte, error) {
	return json.Marshal(struct {
		EventID            string                        `json:"event_id"`
		EventType          string                        `json:"event_type"`
		RuntimeID          string                        `json:"runtime_id,omitempty"`
		ExecutionID        string                        `json:"execution_id,omitempty"`
		OccurredAt         string                        `json:"occurred_at"`
		TraceID            string                        `json:"trace_id,omitempty"`
		CorrelationContext *runtimev1.CorrelationContext `json:"correlation_context,omitempty"`
		Payload            any                           `json:"payload,omitempty"`
	}{
		EventID:            e.EventID,
		EventType:          e.EventType,
		RuntimeID:          e.RuntimeID,
		ExecutionID:        e.ExecutionID,
		OccurredAt:         e.OccurredAt.Format(time.RFC3339Nano),
		TraceID:            e.TraceID,
		CorrelationContext: e.CorrelationContext,
		Payload:            e.Payload,
	})
}

func RuntimeEventFromEnvelope(envelope Envelope, eventType runtimev1.RuntimeEventType, newState runtimev1.RuntimeState, details string) *runtimev1.RuntimeEvent {
	return &runtimev1.RuntimeEvent{
		EventId:     envelope.EventID,
		RuntimeId:   envelope.RuntimeID,
		ExecutionId: envelope.ExecutionID,
		EventType:   eventType,
		OccurredAt:  timestamppb.New(envelope.OccurredAt),
		DetailsJson: details,
		NewState:    newState,
	}
}
