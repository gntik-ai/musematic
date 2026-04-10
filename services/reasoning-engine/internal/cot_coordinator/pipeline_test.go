package cot_coordinator

import (
	"context"
	"io"
	"strconv"
	"sync"
	"testing"
	"time"
)

type fakeStream struct {
	events []*TraceEvent
	index  int
}

func (s *fakeStream) Context() context.Context { return context.Background() }

func (s *fakeStream) Recv() (*TraceEvent, error) {
	if s.index >= len(s.events) {
		return nil, io.EOF
	}
	event := s.events[s.index]
	s.index++
	return event, nil
}

type fakeRepository struct {
	mu        sync.Mutex
	traceIDs  []string
	events    []TraceEventRecord
	finalized int
	sleep     time.Duration
}

func (r *fakeRepository) EnsureTrace(_ context.Context, executionID string, _ time.Time) (string, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	traceID := executionID + "-trace"
	r.traceIDs = append(r.traceIDs, traceID)
	return traceID, nil
}

func (r *fakeRepository) InsertEvent(_ context.Context, _ string, event TraceEventRecord) error {
	if r.sleep > 0 {
		time.Sleep(r.sleep)
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.events = append(r.events, event)
	return nil
}

func (r *fakeRepository) FinalizeTrace(context.Context, string, int32, int32, time.Time, string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.finalized++
	return nil
}

type fakeUploader struct {
	mu       sync.Mutex
	uploaded []string
	err      error
}

func (u *fakeUploader) Upload(_ context.Context, key string, _ []byte) error {
	if u.err != nil {
		return u.err
	}
	u.mu.Lock()
	defer u.mu.Unlock()
	u.uploaded = append(u.uploaded, key)
	return nil
}

func (u *fakeUploader) GetURL(key string) string { return key }

type fakeProducer struct {
	mu     sync.Mutex
	events int
	err    error
}

func (p *fakeProducer) Produce(context.Context, string, string, []byte) error {
	if p.err != nil {
		return p.err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.events++
	return nil
}

func TestPipelineProcessStreamPersistsAndPublishes(t *testing.T) {
	repo := &fakeRepository{}
	producer := &fakeProducer{}
	pipeline := NewPipeline(repo, producer, nil, nil, 16, 64*1024)

	events := make([]*TraceEvent, 0, 10)
	for i := 0; i < 10; i++ {
		events = append(events, &TraceEvent{
			ExecutionID: "exec-1",
			StepID:      "step-1",
			EventID:     "event-" + strconv.Itoa(i),
			EventType:   "reasoning_step",
			SequenceNum: int32(i + 1),
			Payload:     []byte("small payload"),
			OccurredAt:  time.Now().UTC(),
		})
	}

	ack, err := pipeline.ProcessStream(context.Background(), &fakeStream{events: events})
	if err != nil {
		t.Fatalf("ProcessStream() error = %v", err)
	}
	if ack.TotalReceived != 10 || ack.TotalPersisted != 10 || ack.TotalDropped != 0 {
		t.Fatalf("unexpected ack: %+v", ack)
	}
	if producer.events != 10 {
		t.Fatalf("produced events = %d, want 10", producer.events)
	}
	if repo.finalized != 1 {
		t.Fatalf("FinalizeTrace() count = %d, want 1", repo.finalized)
	}
}

func TestPipelineUploadsLargePayloads(t *testing.T) {
	repo := &fakeRepository{}
	uploader := &fakeUploader{}
	pipeline := NewPipeline(repo, nil, uploader, nil, 4, 8)

	ack, err := pipeline.ProcessStream(context.Background(), &fakeStream{events: []*TraceEvent{{
		ExecutionID: "exec-2",
		StepID:      "step-1",
		EventID:     "event-1",
		EventType:   "reasoning_step",
		SequenceNum: 1,
		Payload:     []byte("this payload is definitely larger than the threshold"),
		OccurredAt:  time.Now().UTC(),
	}}})
	if err != nil {
		t.Fatalf("ProcessStream() error = %v", err)
	}
	if ack.TotalPersisted != 1 {
		t.Fatalf("persisted = %d, want 1", ack.TotalPersisted)
	}
	if len(uploader.uploaded) != 1 {
		t.Fatalf("uploads = %d, want 1", len(uploader.uploaded))
	}
	if repo.events[0].ObjectKey == "" {
		t.Fatal("expected object key to be stored for large payload")
	}
}

func TestPipelineDropsOldestWhenBufferOverflows(t *testing.T) {
	repo := &fakeRepository{sleep: 20 * time.Millisecond}
	pipeline := NewPipeline(repo, nil, nil, nil, 1, 64*1024)

	events := []*TraceEvent{
		{ExecutionID: "exec-3", StepID: "step-1", EventID: "e1", EventType: "step", SequenceNum: 1, Payload: []byte("1"), OccurredAt: time.Now().UTC()},
		{ExecutionID: "exec-3", StepID: "step-1", EventID: "e2", EventType: "step", SequenceNum: 2, Payload: []byte("2"), OccurredAt: time.Now().UTC()},
		{ExecutionID: "exec-3", StepID: "step-1", EventID: "e3", EventType: "step", SequenceNum: 3, Payload: []byte("3"), OccurredAt: time.Now().UTC()},
		{ExecutionID: "exec-3", StepID: "step-1", EventID: "e4", EventType: "step", SequenceNum: 4, Payload: []byte("4"), OccurredAt: time.Now().UTC()},
	}

	ack, err := pipeline.ProcessStream(context.Background(), &fakeStream{events: events})
	if err != nil {
		t.Fatalf("ProcessStream() error = %v", err)
	}
	if ack.TotalDropped == 0 {
		t.Fatalf("expected dropped events, got %+v", ack)
	}
}

func TestPGTraceRepositoryNilPoolIsSafe(t *testing.T) {
	repo := NewPGTraceRepository(nil)
	traceID, err := repo.EnsureTrace(context.Background(), "exec-4", time.Now())
	if err != nil {
		t.Fatalf("EnsureTrace() error = %v", err)
	}
	if traceID == "" {
		t.Fatal("expected deterministic trace id")
	}
	if err := repo.InsertEvent(context.Background(), traceID, TraceEventRecord{}); err != nil {
		t.Fatalf("InsertEvent() error = %v", err)
	}
	if err := repo.FinalizeTrace(context.Background(), "exec-4", 1, 0, time.Now(), ""); err != nil {
		t.Fatalf("FinalizeTrace() error = %v", err)
	}
	if nullIfEmpty("") != nil {
		t.Fatal("nullIfEmpty() should return nil for empty string")
	}
}

func TestPipelineRecordsFailures(t *testing.T) {
	t.Run("uploader error", func(t *testing.T) {
		pipeline := NewPipeline(&fakeRepository{}, nil, &fakeUploader{err: io.ErrUnexpectedEOF}, nil, 4, 1)
		ack, err := pipeline.ProcessStream(context.Background(), &fakeStream{events: []*TraceEvent{{
			ExecutionID: "exec-5",
			StepID:      "step-1",
			EventID:     "event-1",
			EventType:   "step",
			SequenceNum: 1,
			Payload:     []byte("large payload"),
			OccurredAt:  time.Now().UTC(),
		}}})
		if err != nil {
			t.Fatalf("ProcessStream() error = %v", err)
		}
		if len(ack.FailedEventIDs) != 1 {
			t.Fatalf("failed events = %+v", ack.FailedEventIDs)
		}
	})

	t.Run("producer error", func(t *testing.T) {
		pipeline := NewPipeline(&fakeRepository{}, &fakeProducer{err: io.ErrClosedPipe}, nil, nil, 4, 64*1024)
		ack, err := pipeline.ProcessStream(context.Background(), &fakeStream{events: []*TraceEvent{{
			ExecutionID: "exec-6",
			StepID:      "step-1",
			EventID:     "event-1",
			EventType:   "step",
			SequenceNum: 1,
			Payload:     []byte("payload"),
			OccurredAt:  time.Now().UTC(),
		}}})
		if err != nil {
			t.Fatalf("ProcessStream() error = %v", err)
		}
		if len(ack.FailedEventIDs) != 1 {
			t.Fatalf("failed events = %+v", ack.FailedEventIDs)
		}
	})
}
