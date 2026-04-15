package warmpool

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	v1 "k8s.io/api/core/v1"
)

type fakeWarmPoolInserter struct {
	inserted []state.WarmPoolPod
}

func (f *fakeWarmPoolInserter) InsertWarmPoolPod(_ context.Context, pod state.WarmPoolPod) error {
	f.inserted = append(f.inserted, pod)
	return nil
}

type fakeWarmPoolPods struct {
	created []*v1.Pod
	phase   v1.PodPhase
	err     error
}

func (f *fakeWarmPoolPods) CreatePod(_ context.Context, pod *v1.Pod) (*v1.Pod, error) {
	if f.err != nil {
		return nil, f.err
	}
	f.created = append(f.created, pod)
	return pod, nil
}

func (f *fakeWarmPoolPods) GetPod(context.Context, string) (*v1.Pod, error) {
	phase := f.phase
	if phase == "" {
		phase = v1.PodRunning
	}
	return &v1.Pod{Status: v1.PodStatus{Phase: phase}}, nil
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

func TestReconcileOnceCreatesKubernetesWarmPods(t *testing.T) {
	store := &fakeWarmPoolInserter{}
	pods := &fakeWarmPoolPods{}
	manager := NewManager()
	replenisher := &Replenisher{Store: store, Manager: manager, Pods: pods, Namespace: "runtime-ns"}

	replenisher.ReconcileOnce(context.Background(), map[string]int{"ws-1/agent-a": 1})

	if len(pods.created) != 1 {
		t.Fatalf("expected one created pod, got %d", len(pods.created))
	}
	if pods.created[0].Namespace != "runtime-ns" || pods.created[0].Labels["warm_pool"] != "warming" {
		t.Fatalf("unexpected warm pod: %+v", pods.created[0])
	}
	if len(store.inserted) != 1 || store.inserted[0].Status != "ready" {
		t.Fatalf("expected ready warm pod persistence, got %+v", store.inserted)
	}
	if count := manager.Count("ws-1", "agent-a"); count != 1 {
		t.Fatalf("expected ready pod in manager, got %d", count)
	}
}

func TestReconcileOnceHandlesWarmingAndCreateErrors(t *testing.T) {
	store := &fakeWarmPoolInserter{}
	manager := NewManager()
	replenisher := &Replenisher{Store: store, Manager: manager, Pods: &fakeWarmPoolPods{phase: v1.PodPending}}

	replenisher.ReconcileOnce(context.Background(), map[string]int{"ws-1/agent-a": 1})
	if len(store.inserted) != 1 || store.inserted[0].Status != "warming" {
		t.Fatalf("expected warming pod persistence, got %+v", store.inserted)
	}
	if count := manager.Count("ws-1", "agent-a"); count != 0 {
		t.Fatalf("warming pod should not be registered ready, got %d", count)
	}

	store = &fakeWarmPoolInserter{}
	replenisher = &Replenisher{Store: store, Manager: NewManager(), Pods: &fakeWarmPoolPods{err: errors.New("create failed")}}
	replenisher.ReconcileOnce(context.Background(), map[string]int{"ws-1/agent-a": 1})
	if len(store.inserted) != 0 {
		t.Fatalf("failed pod creation should not persist warm pod, got %+v", store.inserted)
	}
}

func TestSplitKeyAndSanitize(t *testing.T) {
	workspace, agent := splitKey("ws-1/agent-a")
	if workspace != "ws-1" || agent != "agent-a" {
		t.Fatalf("unexpected split result: %s %s", workspace, agent)
	}
	workspace, agent = splitKey("ws-only")
	if workspace != "ws-only" || agent != "" {
		t.Fatalf("unexpected no-slash split result: %s %s", workspace, agent)
	}
	if sanitize("") != "default" || sanitize("value") != "value" {
		t.Fatalf("unexpected sanitize behavior")
	}
	if ns := namespaceOrDefault(""); ns != "platform-execution" {
		t.Fatalf("unexpected default namespace: %s", ns)
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
