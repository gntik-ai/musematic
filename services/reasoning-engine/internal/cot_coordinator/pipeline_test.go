package cot_coordinator

import (
	"context"
	"errors"
	"io"
	"strconv"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

type fakeStream struct {
	events []*TraceEvent
	index  int
	err    error
}

func (s *fakeStream) Context() context.Context { return context.Background() }

func (s *fakeStream) Recv() (*TraceEvent, error) {
	if s.err != nil {
		return nil, s.err
	}
	if s.index >= len(s.events) {
		return nil, io.EOF
	}
	event := s.events[s.index]
	s.index++
	return event, nil
}

type fakeRepository struct {
	mu          sync.Mutex
	traceIDs    []string
	events      []TraceEventRecord
	finalized   int
	sleep       time.Duration
	ensureErr   error
	insertErr   error
	finalizeErr error
}

func (r *fakeRepository) EnsureTrace(_ context.Context, executionID string, _ time.Time) (string, error) {
	if r.ensureErr != nil {
		return "", r.ensureErr
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	traceID := executionID + "-trace"
	r.traceIDs = append(r.traceIDs, traceID)
	return traceID, nil
}

func (r *fakeRepository) InsertEvent(_ context.Context, _ string, event TraceEventRecord) error {
	if r.insertErr != nil {
		return r.insertErr
	}
	if r.sleep > 0 {
		time.Sleep(r.sleep)
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.events = append(r.events, event)
	return nil
}

func (r *fakeRepository) FinalizeTrace(context.Context, string, int32, int32, time.Time, string) error {
	if r.finalizeErr != nil {
		return r.finalizeErr
	}
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
	mu            sync.Mutex
	events        int
	err           error
	reactEvents   int
	reactErr      error
	reactPayloads []map[string]any
	reactBlock    <-chan struct{}
	reactDone     chan map[string]any
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

func (p *fakeProducer) ProduceReactCycleCompleted(_ context.Context, _ string, payload map[string]any) error {
	if p.reactBlock != nil {
		<-p.reactBlock
	}
	if p.reactErr != nil {
		return p.reactErr
	}
	copyPayload := make(map[string]any, len(payload))
	for key, value := range payload {
		copyPayload[key] = value
	}
	p.mu.Lock()
	p.reactEvents++
	p.reactPayloads = append(p.reactPayloads, copyPayload)
	p.mu.Unlock()
	if p.reactDone != nil {
		select {
		case p.reactDone <- copyPayload:
		default:
		}
	}
	return nil
}

type fakeBatchResults struct {
	execErr  error
	closeErr error
}

func (b *fakeBatchResults) Exec() (pgconn.CommandTag, error) {
	return pgconn.NewCommandTag("INSERT 0 1"), b.execErr
}

func (b *fakeBatchResults) Query() (pgx.Rows, error) {
	return nil, nil
}

func (b *fakeBatchResults) QueryRow() pgx.Row {
	return nil
}

func (b *fakeBatchResults) Close() error {
	return b.closeErr
}

type fakeTraceStore struct {
	execErr   error
	batch     *fakeBatchResults
	execSQL   []string
	execArgs  [][]any
	sentBatch *pgx.Batch
}

func (s *fakeTraceStore) Exec(_ context.Context, sql string, arguments ...any) (pgconn.CommandTag, error) {
	s.execSQL = append(s.execSQL, sql)
	s.execArgs = append(s.execArgs, arguments)
	return pgconn.NewCommandTag("OK"), s.execErr
}

func (s *fakeTraceStore) SendBatch(_ context.Context, batch *pgx.Batch) pgx.BatchResults {
	s.sentBatch = batch
	if s.batch == nil {
		s.batch = &fakeBatchResults{}
	}
	return s.batch
}

func TestPipelineProcessStreamPersistsAndPublishes(t *testing.T) {
	repo := &fakeRepository{}
	producer := &fakeProducer{}
	pipeline := NewPipeline(repo, producer, nil, nil, 16, 64*1024)

	events := make([]*TraceEvent, 0, 10)
	for i := int32(0); i < 10; i++ {
		events = append(events, &TraceEvent{
			ExecutionID: "exec-1",
			StepID:      "step-1",
			EventID:     "event-" + strconv.Itoa(int(i)),
			EventType:   "reasoning_step",
			SequenceNum: i + 1,
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
	pipeline.workerCount = 1

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

func TestPipelineDefaultConfigAndErrors(t *testing.T) {
	pipeline := NewPipeline(nil, nil, nil, nil, 0, 0)
	if pipeline.bufferSize != 1 || pipeline.payloadThreshold != 64*1024 {
		t.Fatalf("unexpected defaults: buffer=%d threshold=%d", pipeline.bufferSize, pipeline.payloadThreshold)
	}

	if _, err := pipeline.ProcessStream(context.Background(), &fakeStream{err: io.ErrUnexpectedEOF}); err != io.ErrUnexpectedEOF {
		t.Fatalf("ProcessStream() error = %v, want %v", err, io.ErrUnexpectedEOF)
	}

	if _, err := NewPipeline(&fakeRepository{finalizeErr: errors.New("finalize failed")}, nil, nil, nil, 1, 1).ProcessStream(context.Background(), &fakeStream{events: []*TraceEvent{{
		ExecutionID: "exec-finalize",
		StepID:      "step-1",
		EventID:     "event-1",
		EventType:   "step",
		SequenceNum: 1,
		Payload:     []byte("payload"),
		OccurredAt:  time.Now().UTC(),
	}}}); err == nil {
		t.Fatal("expected finalize error")
	}

	ack, err := NewPipeline(&fakeRepository{ensureErr: errors.New("ensure failed")}, nil, nil, nil, 1, 1).ProcessStream(context.Background(), &fakeStream{events: []*TraceEvent{{
		ExecutionID: "exec-ensure",
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
	if len(ack.FailedEventIDs) != 1 || ack.TotalPersisted != 0 {
		t.Fatalf("unexpected ack = %+v", ack)
	}

	ack, err = NewPipeline(&fakeRepository{insertErr: errors.New("insert failed")}, nil, nil, nil, 1, 1).ProcessStream(context.Background(), &fakeStream{events: []*TraceEvent{{
		ExecutionID: "exec-insert",
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
		t.Fatalf("unexpected ack = %+v", ack)
	}
}

func TestPGTraceRepositoryExecPaths(t *testing.T) { //nolint:gocyclo // This test intentionally exercises the repository persistence branches end to end.
	t.Run("ensure trace persists deterministic ids", func(t *testing.T) {
		store := &fakeTraceStore{}
		repo := &PGTraceRepository{pool: store}

		traceID, err := repo.EnsureTrace(context.Background(), "exec-7", time.Unix(1, 0).UTC())
		if err != nil {
			t.Fatalf("EnsureTrace() error = %v", err)
		}
		if traceID == "" {
			t.Fatal("expected trace id")
		}
		if len(store.execSQL) != 1 {
			t.Fatalf("exec count = %d, want 1", len(store.execSQL))
		}
		if len(store.execArgs[0]) != 4 {
			t.Fatalf("exec args = %d, want 4", len(store.execArgs[0]))
		}
	})

	t.Run("ensure trace returns store error", func(t *testing.T) {
		repo := &PGTraceRepository{pool: &fakeTraceStore{execErr: errors.New("insert failed")}}
		if _, err := repo.EnsureTrace(context.Background(), "exec-7", time.Now().UTC()); err == nil {
			t.Fatal("expected EnsureTrace() error")
		}
	})

	t.Run("insert event batches payload metadata", func(t *testing.T) {
		store := &fakeTraceStore{}
		repo := &PGTraceRepository{pool: store}

		err := repo.InsertEvent(context.Background(), "exec-7-trace", TraceEventRecord{
			EventType:   "step",
			SequenceNum: 2,
			OccurredAt:  time.Unix(2, 0).UTC(),
			PayloadSize: 128,
			ObjectKey:   "reasoning-traces/object.json",
		})
		if err != nil {
			t.Fatalf("InsertEvent() error = %v", err)
		}
		if store.sentBatch == nil || store.sentBatch.Len() != 1 {
			t.Fatalf("sent batch len = %v, want 1", store.sentBatch)
		}
		if got := store.sentBatch.QueuedQueries[0].Arguments[5]; got != "reasoning-traces/object.json" {
			t.Fatalf("object key argument = %#v", got)
		}
	})

	t.Run("insert event returns batch exec error", func(t *testing.T) {
		store := &fakeTraceStore{batch: &fakeBatchResults{execErr: errors.New("batch failed")}}
		repo := &PGTraceRepository{pool: store}
		if err := repo.InsertEvent(context.Background(), "exec-7-trace", TraceEventRecord{}); err == nil {
			t.Fatal("expected InsertEvent() error")
		}
	})

	t.Run("finalize trace updates object key", func(t *testing.T) {
		store := &fakeTraceStore{}
		repo := &PGTraceRepository{pool: store}
		if err := repo.FinalizeTrace(context.Background(), "exec-8", 3, 1, time.Unix(3, 0).UTC(), "archive.json"); err != nil {
			t.Fatalf("FinalizeTrace() error = %v", err)
		}
		if got := store.execArgs[0][4]; got != "archive.json" {
			t.Fatalf("object key arg = %#v", got)
		}
	})

	t.Run("finalize trace returns store error", func(t *testing.T) {
		repo := &PGTraceRepository{pool: &fakeTraceStore{execErr: errors.New("update failed")}}
		if err := repo.FinalizeTrace(context.Background(), "exec-8", 3, 1, time.Now().UTC(), ""); err == nil {
			t.Fatal("expected FinalizeTrace() error")
		}
	})

	if got := nullIfEmpty("object-key"); got != "object-key" {
		t.Fatalf("nullIfEmpty(non-empty) = %#v", got)
	}
	if got := uuidFor("123e4567-e89b-12d3-a456-426614174000").String(); got != "123e4567-e89b-12d3-a456-426614174000" {
		t.Fatalf("uuidFor(valid) = %s", got)
	}
}

func TestPipelineEmitsReactCycleCompletedEvent(t *testing.T) {
	repo := &fakeRepository{}
	producer := &fakeProducer{reactDone: make(chan map[string]any, 1)}
	pipeline := NewPipeline(repo, producer, nil, nil, 4, 64*1024)

	ack, err := pipeline.ProcessStream(context.Background(), &fakeStream{events: []*TraceEvent{{
		ExecutionID: "exec-react",
		StepID:      "step-react",
		EventID:     "event-react-1",
		EventType:   "react_cycle_completed",
		SequenceNum: 1,
		Payload:     []byte(`{"cycle_number":2,"thought":"inspect","action":"call","observation":"ok"}`),
		OccurredAt:  time.Now().UTC(),
	}}})
	if err != nil {
		t.Fatalf("ProcessStream() error = %v", err)
	}
	if ack.TotalPersisted != 1 {
		t.Fatalf("persisted = %d, want 1", ack.TotalPersisted)
	}
	select {
	case payload := <-producer.reactDone:
		if producer.reactEvents != 1 {
			t.Fatalf("react events = %d, want 1", producer.reactEvents)
		}
		if payload["step_id"] != "step-react" || payload["event_id"] != "event-react-1" {
			t.Fatalf("unexpected payload identifiers: %+v", payload)
		}
		if payload["cycle_number"] != float64(2) {
			t.Fatalf("cycle_number = %#v, want 2", payload["cycle_number"])
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for react cycle event")
	}
}

func TestPipelineReactCycleEmissionDoesNotBlockReasoning(t *testing.T) {
	repo := &fakeRepository{}
	block := make(chan struct{})
	producer := &fakeProducer{reactBlock: block, reactDone: make(chan map[string]any, 1)}
	pipeline := NewPipeline(repo, producer, nil, nil, 4, 64*1024)

	done := make(chan error, 1)
	go func() {
		_, err := pipeline.ProcessStream(context.Background(), &fakeStream{events: []*TraceEvent{{
			ExecutionID: "exec-react",
			StepID:      "step-react",
			EventID:     "event-react-2",
			EventType:   "react_cycle_completed",
			SequenceNum: 2,
			Payload:     []byte(`{"cycle_number":3}`),
			OccurredAt:  time.Now().UTC(),
		}}})
		done <- err
	}()

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("ProcessStream() error = %v", err)
		}
	case <-time.After(200 * time.Millisecond):
		close(block)
		t.Fatal("ProcessStream blocked on react event emission")
	}

	close(block)
	select {
	case <-producer.reactDone:
	case <-time.After(time.Second):
		t.Fatal("react cycle event was not delivered after unblocking producer")
	}
}
