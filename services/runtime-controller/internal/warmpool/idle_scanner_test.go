package warmpool

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/google/uuid"
)

type fakeIdleStore struct {
	pods    []state.WarmPoolPod
	updated []string
}

func (f *fakeIdleStore) ListWarmPoolPodsByStatus(context.Context, string) ([]state.WarmPoolPod, error) {
	return f.pods, nil
}

type fakeIdlePods struct{ deleted []string }

func (f *fakeIdlePods) DeletePod(_ context.Context, podName string, _ int64) error {
	f.deleted = append(f.deleted, podName)
	return nil
}

func (f *fakeIdleStore) UpdateWarmPoolPodStatus(_ context.Context, podName string, _ string, _ *uuid.UUID) error {
	f.updated = append(f.updated, podName)
	return nil
}

func TestIdleScannerRecyclesExpiredPods(t *testing.T) {
	old := time.Now().Add(-10 * time.Minute)
	recent := time.Now().Add(-30 * time.Second)
	store := &fakeIdleStore{pods: []state.WarmPoolPod{
		{WorkspaceID: "ws-1", AgentType: "agent-a", PodName: "old-pod", IdleSince: &old},
		{WorkspaceID: "ws-1", AgentType: "agent-a", PodName: "recent-pod", IdleSince: &recent},
		{PodName: "no-idle"},
	}}
	pods := &fakeIdlePods{}
	manager := NewManager()
	manager.RegisterReadyPod("ws-1", "agent-a", "old-pod")
	scanner := &IdleScanner{
		Store:       store,
		IdleTimeout: 5 * time.Minute,
		Pods:        pods,
		Manager:     manager,
	}

	if err := scanner.ScanOnce(context.Background()); err != nil {
		t.Fatalf("ScanOnce returned error: %v", err)
	}
	if len(store.updated) != 1 || store.updated[0] != "old-pod" {
		t.Fatalf("unexpected recycled pods: %+v", store.updated)
	}
	if len(pods.deleted) != 1 || pods.deleted[0] != "old-pod" {
		t.Fatalf("unexpected deleted pods: %+v", pods.deleted)
	}
	if count := manager.Count("ws-1", "agent-a"); count != 0 {
		t.Fatalf("expected manager to remove recycled pod, got %d", count)
	}
}

func TestIdleScannerRunStopsOnContextCancellation(t *testing.T) {
	scanner := &IdleScanner{
		Interval:    time.Millisecond,
		IdleTimeout: time.Minute,
		Store:       &fakeIdleStore{},
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	if err := scanner.Run(ctx); !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context cancellation, got %v", err)
	}
}
