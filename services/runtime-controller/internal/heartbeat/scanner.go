package heartbeat

import (
	"context"
	"log/slog"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/andrea-mucci/musematic/services/runtime-controller/pkg/metrics"
	"github.com/redis/go-redis/v9"
)

type RedisExistenceChecker interface {
	Exists(context.Context, ...string) *redis.IntCmd
}

type Scanner struct {
	Redis RedisExistenceChecker
	Store interface {
		ListActiveRuntimes(context.Context) ([]state.RuntimeRecord, error)
		UpdateRuntimeState(context.Context, string, string, string) error
		InsertRuntimeEvent(context.Context, state.RuntimeEventRecord) error
	}
	Interval time.Duration
	Timeout  time.Duration
	Emitter  *events.EventEmitter
	Fanout   *events.FanoutRegistry
	Logger   *slog.Logger
	Metrics  *metrics.Registry
	Now      func() time.Time
}

func (s *Scanner) Run(ctx context.Context) error {
	ticker := time.NewTicker(s.Interval)
	defer ticker.Stop()
	for {
		if err := s.ScanOnce(ctx); err != nil && s.Logger != nil {
			s.Logger.Error("heartbeat scan failed", "error", err)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (s *Scanner) ScanOnce(ctx context.Context) error {
	runtimes, err := s.Store.ListActiveRuntimes(ctx)
	if err != nil {
		return err
	}
	now := s.now()
	for _, runtime := range runtimes {
		exists, err := s.Redis.Exists(ctx, heartbeatKey(runtime.ExecutionID)).Result()
		if err != nil {
			return err
		}
		if exists > 0 {
			continue
		}
		if !s.timedOut(runtime, now) {
			continue
		}
		if err := s.Store.UpdateRuntimeState(ctx, runtime.ExecutionID, "failed", "heartbeat_timeout"); err != nil {
			return err
		}
		if s.Metrics != nil {
			s.Metrics.IncHeartbeatTimeouts()
		}
		envelope := events.BuildEnvelope("runtime.failed", runtime.RuntimeID.String(), runtime.ExecutionID, &runtimev1.CorrelationContext{
			WorkspaceId: runtime.WorkspaceID,
			ExecutionId: runtime.ExecutionID,
		}, map[string]string{"reason": "heartbeat_timeout"})
		event := events.RuntimeEventFromEnvelope(envelope, runtimev1.RuntimeEventType_RUNTIME_EVENT_FAILED, runtimev1.RuntimeState_RUNTIME_STATE_FAILED, "heartbeat_timeout")
		_ = s.Store.InsertRuntimeEvent(ctx, state.RuntimeEventRecord{
			RuntimeID:   runtime.RuntimeID,
			ExecutionID: runtime.ExecutionID,
			EventType:   "runtime.failed",
			Payload:     []byte(`{"reason":"heartbeat_timeout"}`),
		})
		if s.Emitter != nil {
			_ = s.Emitter.EmitLifecycle(ctx, event, envelope)
		}
		if s.Fanout != nil {
			s.Fanout.Publish(event)
		}
	}
	return nil
}

func (s *Scanner) now() time.Time {
	if s.Now != nil {
		return s.Now().UTC()
	}
	return time.Now().UTC()
}

func (s *Scanner) timedOut(runtime state.RuntimeRecord, now time.Time) bool {
	timeout := s.Timeout
	if timeout <= 0 {
		timeout = time.Minute
	}
	reference := runtime.CreatedAt
	if runtime.LaunchedAt != nil {
		reference = *runtime.LaunchedAt
	}
	if runtime.LastHeartbeatAt != nil {
		reference = *runtime.LastHeartbeatAt
	}
	if reference.IsZero() {
		return true
	}
	return !reference.Add(timeout).After(now)
}
