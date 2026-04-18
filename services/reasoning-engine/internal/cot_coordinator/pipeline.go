package cot_coordinator

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"runtime"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/musematic/reasoning-engine/pkg/metrics"
)

type Pipeline struct {
	repository       TraceRepository
	producer         EventProducer
	uploader         ObjectUploader
	metrics          *metrics.Metrics
	bufferSize       int
	payloadThreshold int
	now              func() time.Time
}

func NewPipeline(repository TraceRepository, producer EventProducer, uploader ObjectUploader, telemetry *metrics.Metrics, bufferSize, payloadThreshold int) *Pipeline {
	if bufferSize <= 0 {
		bufferSize = 1
	}
	if payloadThreshold <= 0 {
		payloadThreshold = 64 * 1024
	}
	return &Pipeline{
		repository:       repository,
		producer:         producer,
		uploader:         uploader,
		metrics:          telemetry,
		bufferSize:       bufferSize,
		payloadThreshold: payloadThreshold,
		now:              func() time.Time { return time.Now().UTC() },
	}
}

//nolint:gocyclo // This method coordinates the full trace streaming pipeline end to end.
func (p *Pipeline) ProcessStream(ctx context.Context, stream TraceStream) (*TraceAck, error) {
	type queuedEvent struct {
		event *TraceEvent
	}

	ack := &TraceAck{}
	queue := make(chan queuedEvent, p.bufferSize)
	var once sync.Once
	var traceID string
	var traceErr error
	var dropped int32
	var mu sync.Mutex
	var workers sync.WaitGroup

	workerCount := runtime.NumCPU()
	if workerCount > 8 {
		workerCount = 8
	}
	if workerCount <= 0 {
		workerCount = 1
	}

	process := func(item queuedEvent) {
		event := item.event
		if event == nil {
			return
		}

		once.Do(func() {
			if p.repository != nil {
				traceID, traceErr = p.repository.EnsureTrace(ctx, event.ExecutionID, event.OccurredAt)
			}
		})
		if traceErr != nil {
			mu.Lock()
			ack.FailedEventIDs = append(ack.FailedEventIDs, event.EventID)
			mu.Unlock()
			return
		}

		objectKey := ""
		if len(event.Payload) > p.payloadThreshold && p.uploader != nil {
			objectKey = fmt.Sprintf("reasoning-traces/%s/%s/%s", event.ExecutionID, event.StepID, event.EventID)
			if err := p.uploader.Upload(ctx, objectKey, event.Payload); err != nil {
				mu.Lock()
				ack.FailedEventIDs = append(ack.FailedEventIDs, event.EventID)
				mu.Unlock()
				return
			}
		}

		if p.repository != nil {
			if err := p.repository.InsertEvent(ctx, traceID, TraceEventRecord{
				EventType:   event.EventType,
				SequenceNum: event.SequenceNum,
				OccurredAt:  event.OccurredAt,
				PayloadSize: len(event.Payload),
				ObjectKey:   objectKey,
			}); err != nil {
				mu.Lock()
				ack.FailedEventIDs = append(ack.FailedEventIDs, event.EventID)
				mu.Unlock()
				return
			}
		}

		if p.producer != nil {
			payload, _ := json.Marshal(map[string]any{
				"event_type":   "reasoning.trace_event",
				"version":      "1.0",
				"source":       "reasoning-engine",
				"execution_id": event.ExecutionID,
				"occurred_at":  event.OccurredAt.Format(time.RFC3339Nano),
				"payload": map[string]any{
					"step_id":      event.StepID,
					"event_id":     event.EventID,
					"event_type":   event.EventType,
					"sequence_num": event.SequenceNum,
					"payload_size": len(event.Payload),
					"object_key":   objectKey,
				},
			})
			if err := p.producer.Produce(ctx, "runtime.reasoning", event.ExecutionID, payload); err != nil {
				mu.Lock()
				ack.FailedEventIDs = append(ack.FailedEventIDs, event.EventID)
				mu.Unlock()
				return
			}
		}

		p.metrics.RecordTraceEvent(ctx)
		mu.Lock()
		ack.ExecutionID = event.ExecutionID
		ack.TotalPersisted++
		mu.Unlock()
	}

	for i := 0; i < workerCount; i++ {
		workers.Add(1)
		go func() {
			defer workers.Done()
			for item := range queue {
				process(item)
			}
		}()
	}

	for {
		event, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			close(queue)
			workers.Wait()
			return nil, err
		}

		mu.Lock()
		ack.TotalReceived++
		if ack.ExecutionID == "" {
			ack.ExecutionID = event.ExecutionID
		}
		mu.Unlock()

		item := queuedEvent{event: event}
		select {
		case queue <- item:
		default:
			// A worker may drain the queue between hitting the default branch and
			// attempting to evict the oldest buffered item. Re-check with a
			// non-blocking receive so overflow handling never hangs waiting on an
			// already-drained channel.
			select {
			case <-queue:
				dropped++
				p.metrics.RecordTraceDropped(ctx)
			default:
			}
			queue <- item
		}
	}

	close(queue)
	workers.Wait()

	ack.TotalDropped = dropped
	if p.repository != nil && ack.ExecutionID != "" {
		if err := p.repository.FinalizeTrace(ctx, ack.ExecutionID, ack.TotalPersisted, ack.TotalDropped, p.now(), ""); err != nil {
			return nil, err
		}
	}
	return ack, nil
}

type PGTraceRepository struct {
	pool traceStore
}

type traceStore interface {
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
	SendBatch(ctx context.Context, batch *pgx.Batch) pgx.BatchResults
}

func NewPGTraceRepository(pool *pgxpool.Pool) *PGTraceRepository {
	var store traceStore
	if pool != nil {
		store = pool
	}
	return &PGTraceRepository{pool: store}
}

func (r *PGTraceRepository) EnsureTrace(ctx context.Context, executionID string, startedAt time.Time) (string, error) {
	if r == nil || r.pool == nil {
		return uuidFor(executionID).String(), nil
	}

	traceID := uuidFor(executionID)
	execID := uuidFor(executionID)
	_, err := r.pool.Exec(ctx, `
INSERT INTO reasoning_traces (id, execution_id, mode, total_events, dropped_events, started_at)
VALUES ($1, $2, $3, 0, 0, $4)
ON CONFLICT (execution_id) DO NOTHING
`, traceID, execID, "DIRECT", startedAt)
	if err != nil {
		return "", err
	}
	return traceID.String(), nil
}

func (r *PGTraceRepository) InsertEvent(ctx context.Context, traceID string, event TraceEventRecord) error {
	if r == nil || r.pool == nil {
		return nil
	}

	batch := &pgx.Batch{}
	batch.Queue(`
INSERT INTO reasoning_events (trace_id, event_type, sequence_num, occurred_at, payload_size, object_key)
VALUES ($1, $2, $3, $4, $5, $6)
`, uuidFor(traceID), event.EventType, event.SequenceNum, event.OccurredAt, event.PayloadSize, nullIfEmpty(event.ObjectKey))
	results := r.pool.SendBatch(ctx, batch)
	defer func() {
		_ = results.Close()
	}()
	_, err := results.Exec()
	return err
}

func (r *PGTraceRepository) FinalizeTrace(ctx context.Context, executionID string, totalEvents, droppedEvents int32, completedAt time.Time, objectKey string) error {
	if r == nil || r.pool == nil {
		return nil
	}
	_, err := r.pool.Exec(ctx, `
UPDATE reasoning_traces
SET total_events = $2, dropped_events = $3, completed_at = $4, object_key = COALESCE($5, object_key)
WHERE execution_id = $1
`, uuidFor(executionID), totalEvents, droppedEvents, completedAt, nullIfEmpty(objectKey))
	return err
}

func uuidFor(value string) uuid.UUID {
	if parsed, err := uuid.Parse(value); err == nil {
		return parsed
	}
	return uuid.NewMD5(uuid.Nil, []byte(value))
}

func nullIfEmpty(value string) any {
	if value == "" {
		return nil
	}
	return value
}
