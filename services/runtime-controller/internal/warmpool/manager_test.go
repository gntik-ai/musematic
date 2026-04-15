package warmpool

import (
	"context"
	"testing"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/google/uuid"
)

type fakeWarmPoolStore struct {
	pods    []state.WarmPoolPod
	updated []string
}

func (f fakeWarmPoolStore) ListWarmPoolPodsByStatus(context.Context, string) ([]state.WarmPoolPod, error) {
	return f.pods, nil
}

func (f *fakeWarmPoolStore) UpdateWarmPoolPodStatus(_ context.Context, podName string, _ string, _ *uuid.UUID) error {
	f.updated = append(f.updated, podName)
	return nil
}

func TestManagerLoadRegisterDispatchAndCount(t *testing.T) {
	manager := NewManager()
	err := manager.LoadFromDB(context.Background(), fakeWarmPoolStore{pods: []state.WarmPoolPod{
		{WorkspaceID: "ws-1", AgentType: "agent-a", PodName: "pod-1"},
	}})
	if err != nil {
		t.Fatalf("LoadFromDB returned error: %v", err)
	}
	manager.RegisterReadyPod("ws-1", "agent-a", "pod-2")

	if count := manager.Count("ws-1", "agent-a"); count != 2 {
		t.Fatalf("unexpected ready count: %d", count)
	}
	first, ok, err := manager.Dispatch(context.Background(), "ws-1", "agent-a", uuid.New())
	if err != nil {
		t.Fatalf("Dispatch returned error: %v", err)
	}
	if !ok || first != "pod-1" {
		t.Fatalf("unexpected first dispatch: %q %v", first, ok)
	}
	second, ok, err := manager.Dispatch(context.Background(), "ws-1", "agent-a", uuid.New())
	if err != nil {
		t.Fatalf("Dispatch returned error: %v", err)
	}
	if !ok || second != "pod-2" {
		t.Fatalf("unexpected second dispatch: %q %v", second, ok)
	}
	if _, ok, err := manager.Dispatch(context.Background(), "ws-1", "agent-a", uuid.New()); err != nil || ok {
		t.Fatalf("expected empty queue after dispatching all pods")
	}
}

func TestManagerDispatchUpdatesStoreAndRemoveReadyPod(t *testing.T) {
	store := &fakeWarmPoolStore{}
	manager := NewManager(store)
	manager.RegisterReadyPod("ws-1", "agent-a", "pod-1")
	manager.RegisterReadyPod("ws-1", "agent-a", "pod-2")
	manager.RemoveReadyPod("ws-1", "agent-a", "pod-2")

	podName, ok, err := manager.Dispatch(context.Background(), "ws-1", "agent-a", uuid.New())
	if err != nil {
		t.Fatalf("Dispatch returned error: %v", err)
	}
	if !ok || podName != "pod-1" {
		t.Fatalf("unexpected dispatch result: %s %v", podName, ok)
	}
	if len(store.updated) != 1 || store.updated[0] != "pod-1" {
		t.Fatalf("expected store update for dispatch, got %+v", store.updated)
	}
	if count := manager.Count("ws-1", "agent-a"); count != 0 {
		t.Fatalf("expected empty queue, got %d", count)
	}
}
