package warmpool

import (
	"context"
	"testing"
	"time"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
)

type fakeWarmPoolInserter struct {
	inserted []state.WarmPoolPod
}

func (f *fakeWarmPoolInserter) InsertWarmPoolPod(_ context.Context, pod state.WarmPoolPod) error {
	f.inserted = append(f.inserted, pod)
	return nil
}

func TestReconcileOnceCreatesMissingWarmPods(t *testing.T) {
	store := &fakeWarmPoolInserter{}
	manager := NewManager()
	manager.RegisterReadyPod("ws-1", "agent-a", "existing")
	replenisher := &Replenisher{Store: store, Manager: manager}

	replenisher.ReconcileOnce(context.Background(), map[string]int{"ws-1/agent-a": 2, "ws-2/agent-b": 1})

	if count := manager.Count("ws-1", "agent-a"); count != 2 {
		t.Fatalf("unexpected ws-1 count: %d", count)
	}
	if count := manager.Count("ws-2", "agent-b"); count != 1 {
		t.Fatalf("unexpected ws-2 count: %d", count)
	}
	if len(store.inserted) != 2 {
		t.Fatalf("expected 2 inserted warm pool pods, got %d", len(store.inserted))
	}
}

func TestSplitKeyAndSanitize(t *testing.T) {
	workspace, agent := splitKey("ws-1/agent-a")
	if workspace != "ws-1" || agent != "agent-a" {
		t.Fatalf("unexpected split result: %s %s", workspace, agent)
	}
	if sanitize("") != "default" || sanitize("value") != "value" {
		t.Fatalf("unexpected sanitize behavior")
	}
}

func TestReplenisherRunStopsOnContextCancellation(t *testing.T) {
	replenisher := &Replenisher{
		Interval: time.Millisecond,
		Store:    &fakeWarmPoolInserter{},
		Manager:  NewManager(),
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	if err := replenisher.Run(ctx, map[string]int{}); err == nil {
		t.Fatalf("expected canceled context error")
	}
}
