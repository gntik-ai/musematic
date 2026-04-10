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

func (f *fakeIdleStore) UpdateWarmPoolPodStatus(_ context.Context, podName string, _ string, _ *uuid.UUID) error {
	f.updated = append(f.updated, podName)
	return nil
}

func TestIdleScannerRecyclesExpiredPods(t *testing.T) {
	old := time.Now().Add(-10 * time.Minute)
	recent := time.Now().Add(-30 * time.Second)
	store := &fakeIdleStore{pods: []state.WarmPoolPod{
		{PodName: "old-pod", IdleSince: &old},
		{PodName: "recent-pod", IdleSince: &recent},
		{PodName: "no-idle"},
	}}
	scanner := &IdleScanner{
		Store:       store,
		IdleTimeout: 5 * time.Minute,
	}

	if err := scanner.ScanOnce(context.Background()); err != nil {
		t.Fatalf("ScanOnce returned error: %v", err)
	}
	if len(store.updated) != 1 || store.updated[0] != "old-pod" {
		t.Fatalf("unexpected recycled pods: %+v", store.updated)
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
