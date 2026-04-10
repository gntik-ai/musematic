package warmpool

import (
	"context"
	"testing"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
)

type fakeWarmPoolStore struct {
	pods []state.WarmPoolPod
}

func (f fakeWarmPoolStore) ListWarmPoolPodsByStatus(context.Context, string) ([]state.WarmPoolPod, error) {
	return f.pods, nil
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
	first, ok := manager.Dispatch("ws-1", "agent-a")
	if !ok || first != "pod-1" {
		t.Fatalf("unexpected first dispatch: %q %v", first, ok)
	}
	second, ok := manager.Dispatch("ws-1", "agent-a")
	if !ok || second != "pod-2" {
		t.Fatalf("unexpected second dispatch: %q %v", second, ok)
	}
	if _, ok := manager.Dispatch("ws-1", "agent-a"); ok {
		t.Fatalf("expected empty queue after dispatching all pods")
	}
}
