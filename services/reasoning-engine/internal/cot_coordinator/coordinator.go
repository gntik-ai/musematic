package cot_coordinator

import (
	"context"
	"time"
)

type TraceEvent struct {
	ExecutionID string
	StepID      string
	EventID     string
	EventType   string
	SequenceNum int32
	Payload     []byte
	OccurredAt  time.Time
}

type TraceAck struct {
	ExecutionID    string
	TotalReceived  int32
	TotalPersisted int32
	TotalDropped   int32
	FailedEventIDs []string
}

type TraceStream interface {
	Context() context.Context
	Recv() (*TraceEvent, error)
}

type TraceEventRecord struct {
	EventType   string
	SequenceNum int32
	OccurredAt  time.Time
	PayloadSize int
	ObjectKey   string
}

type TraceRepository interface {
	EnsureTrace(ctx context.Context, executionID string, startedAt time.Time) (string, error)
	InsertEvent(ctx context.Context, traceID string, event TraceEventRecord) error
	FinalizeTrace(ctx context.Context, executionID string, totalEvents, droppedEvents int32, completedAt time.Time, objectKey string) error
}

type EventProducer interface {
	Produce(ctx context.Context, topic, key string, value []byte) error
}

type ObjectUploader interface {
	Upload(ctx context.Context, key string, data []byte) error
	GetURL(key string) string
}

type CoTCoordinator interface {
	ProcessStream(ctx context.Context, stream TraceStream) (*TraceAck, error)
}
