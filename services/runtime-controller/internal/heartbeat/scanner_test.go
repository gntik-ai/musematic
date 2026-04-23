package heartbeat

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/andrea-mucci/musematic/services/runtime-controller/pkg/metrics"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

type fakeRedisExists struct {
	values map[string]int64
	err    error
}

func (f *fakeRedisExists) Exists(_ context.Context, keys ...string) *redis.IntCmd {
	if f.err != nil {
		return redis.NewIntResult(0, f.err)
	}
	return redis.NewIntResult(f.values[keys[0]], nil)
}

type fakeScannerStore struct {
	runtimes  []state.RuntimeRecord
	listErr   error
	updateErr error
	eventErr  error
	updates   []struct {
		executionID string
		stateValue  string
		reason      string
	}
	events []state.RuntimeEventRecord
}

func (f *fakeScannerStore) ListActiveRuntimes(context.Context) ([]state.RuntimeRecord, error) {
	return f.runtimes, f.listErr
}

func (f *fakeScannerStore) UpdateRuntimeState(_ context.Context, executionID string, stateValue string, reason string) error {
	if f.updateErr != nil {
		return f.updateErr
	}
	f.updates = append(f.updates, struct {
		executionID string
		stateValue  string
		reason      string
	}{executionID: executionID, stateValue: stateValue, reason: reason})
	return nil
}

func (f *fakeScannerStore) InsertRuntimeEvent(_ context.Context, event state.RuntimeEventRecord) error {
	if f.eventErr != nil {
		return f.eventErr
	}
	f.events = append(f.events, event)
	return nil
}

func TestScanOnceMarksMissingHeartbeatFailedAndPublishes(t *testing.T) {
	now := time.Date(2026, time.April, 22, 22, 40, 0, 0, time.UTC)
	launchedAt := now.Add(-2 * time.Minute)
	record := state.RuntimeRecord{
		RuntimeID:   uuid.New(),
		ExecutionID: "exec-1",
		WorkspaceID: "ws-1",
		LaunchedAt:  &launchedAt,
		CreatedAt:   launchedAt,
	}
	store := &fakeScannerStore{runtimes: []state.RuntimeRecord{record}}
	fanout := events.NewFanoutRegistry()
	ch, unsubscribe := fanout.Subscribe("exec-1")
	defer unsubscribe()
	scanner := &Scanner{
		Redis:   &fakeRedisExists{values: map[string]int64{"heartbeat:exec-1": 0}},
		Store:   store,
		Timeout: time.Minute,
		Fanout:  fanout,
		Metrics: metrics.NewRegistry(),
		Now:     func() time.Time { return now },
	}

	if err := scanner.ScanOnce(context.Background()); err != nil {
		t.Fatalf("ScanOnce returned error: %v", err)
	}
	if len(store.updates) != 1 || store.updates[0].reason != "heartbeat_timeout" {
		t.Fatalf("unexpected state updates: %+v", store.updates)
	}
	if len(store.events) != 1 || store.events[0].EventType != "runtime.failed" {
		t.Fatalf("unexpected stored events: %+v", store.events)
	}
	select {
	case event := <-ch:
		if event.EventType != runtimev1.RuntimeEventType_RUNTIME_EVENT_FAILED {
			t.Fatalf("unexpected fanout event: %+v", event)
		}
	default:
		t.Fatalf("expected fanout event")
	}
}

func TestScanOnceKeepsRecentlyLaunchedRuntimeAliveWithoutHeartbeat(t *testing.T) {
	now := time.Date(2026, time.April, 22, 22, 40, 0, 0, time.UTC)
	launchedAt := now.Add(-30 * time.Second)
	record := state.RuntimeRecord{
		RuntimeID:   uuid.New(),
		ExecutionID: "exec-1",
		WorkspaceID: "ws-1",
		LaunchedAt:  &launchedAt,
		CreatedAt:   launchedAt,
	}
	store := &fakeScannerStore{runtimes: []state.RuntimeRecord{record}}
	scanner := &Scanner{
		Redis:   &fakeRedisExists{values: map[string]int64{"heartbeat:exec-1": 0}},
		Store:   store,
		Timeout: time.Minute,
		Now:     func() time.Time { return now },
	}

	if err := scanner.ScanOnce(context.Background()); err != nil {
		t.Fatalf("ScanOnce returned error: %v", err)
	}
	if len(store.updates) != 0 || len(store.events) != 0 {
		t.Fatalf("expected no updates while heartbeat grace window is still open")
	}
}

func TestScanOnceSkipsActiveHeartbeat(t *testing.T) {
	now := time.Date(2026, time.April, 22, 22, 40, 0, 0, time.UTC)
	launchedAt := now.Add(-2 * time.Minute)
	record := state.RuntimeRecord{
		RuntimeID:   uuid.New(),
		ExecutionID: "exec-1",
		WorkspaceID: "ws-1",
		LaunchedAt:  &launchedAt,
		CreatedAt:   launchedAt,
	}
	store := &fakeScannerStore{runtimes: []state.RuntimeRecord{record}}
	scanner := &Scanner{
		Redis:   &fakeRedisExists{values: map[string]int64{"heartbeat:exec-1": 1}},
		Store:   store,
		Timeout: time.Minute,
		Now:     func() time.Time { return now },
	}

	if err := scanner.ScanOnce(context.Background()); err != nil {
		t.Fatalf("ScanOnce returned error: %v", err)
	}
	if len(store.updates) != 0 || len(store.events) != 0 {
		t.Fatalf("expected no updates for active heartbeat")
	}
}

func TestScanOncePropagatesErrors(t *testing.T) {
	scanner := &Scanner{
		Redis: &fakeRedisExists{err: errors.New("redis down")},
		Store: &fakeScannerStore{runtimes: []state.RuntimeRecord{{
			RuntimeID:   uuid.New(),
			ExecutionID: "exec-1",
			CreatedAt:   time.Now().UTC(),
		}}},
		Timeout: time.Minute,
	}
	if err := scanner.ScanOnce(context.Background()); err == nil {
		t.Fatalf("expected redis error")
	}
}

func TestScanOncePropagatesStoreErrors(t *testing.T) {
	now := time.Date(2026, time.April, 22, 22, 40, 0, 0, time.UTC)
	launchedAt := now.Add(-2 * time.Minute)
	scanner := &Scanner{
		Redis: &fakeRedisExists{values: map[string]int64{"heartbeat:exec-1": 0}},
		Store: &fakeScannerStore{
			runtimes: []state.RuntimeRecord{{
				RuntimeID:   uuid.New(),
				ExecutionID: "exec-1",
				LaunchedAt:  &launchedAt,
				CreatedAt:   launchedAt,
			}},
			updateErr: errors.New("update failed"),
		},
		Timeout: time.Minute,
		Now:     func() time.Time { return now },
	}
	if err := scanner.ScanOnce(context.Background()); err == nil {
		t.Fatalf("expected store update error")
	}
}

func TestScannerRunStopsOnContextCancellation(t *testing.T) {
	scanner := &Scanner{
		Redis:    &fakeRedisExists{values: map[string]int64{}},
		Store:    &fakeScannerStore{},
		Interval: time.Millisecond,
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := scanner.Run(ctx); !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context cancellation, got %v", err)
	}
}

func TestScanOnceContinuesWhenEventPersistenceFails(t *testing.T) {
	now := time.Date(2026, time.April, 22, 22, 40, 0, 0, time.UTC)
	launchedAt := now.Add(-2 * time.Minute)
	record := state.RuntimeRecord{
		RuntimeID:   uuid.New(),
		ExecutionID: "exec-1",
		WorkspaceID: "ws-1",
		LaunchedAt:  &launchedAt,
		CreatedAt:   launchedAt,
	}
	store := &fakeScannerStore{
		runtimes: []state.RuntimeRecord{record},
		eventErr: errors.New("persist failed"),
	}
	fanout := events.NewFanoutRegistry()
	ch, unsubscribe := fanout.Subscribe("exec-1")
	defer unsubscribe()
	scanner := &Scanner{
		Redis:   &fakeRedisExists{values: map[string]int64{"heartbeat:exec-1": 0}},
		Store:   store,
		Timeout: time.Minute,
		Fanout:  fanout,
		Now:     func() time.Time { return now },
	}

	if err := scanner.ScanOnce(context.Background()); err != nil {
		t.Fatalf("ScanOnce returned error: %v", err)
	}
	if len(store.updates) != 1 {
		t.Fatalf("expected runtime update even when persistence fails")
	}
	select {
	case <-ch:
	default:
		t.Fatalf("expected fanout event despite persistence error")
	}
}
