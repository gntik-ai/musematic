package sandbox

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/events"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	"github.com/google/uuid"
	v1 "k8s.io/api/core/v1"
)

type fakePodController struct {
	pods map[string]*v1.Pod
}

func (f *fakePodController) CreatePod(_ context.Context, pod *v1.Pod) (*v1.Pod, error) {
	if f.pods == nil {
		f.pods = map[string]*v1.Pod{}
	}
	copy := pod.DeepCopy()
	copy.Status.Phase = v1.PodRunning
	f.pods[pod.Name] = copy
	return copy, nil
}

func (f *fakePodController) GetPod(_ context.Context, name string) (*v1.Pod, error) {
	if pod, ok := f.pods[name]; ok {
		return pod.DeepCopy(), nil
	}
	return nil, context.Canceled
}

func (f *fakePodController) ListPodsByLabel(context.Context, string) ([]v1.Pod, error) {
	var out []v1.Pod
	for _, pod := range f.pods {
		out = append(out, *pod.DeepCopy())
	}
	return out, nil
}

func (f *fakePodController) DeletePod(_ context.Context, name string, _ int64) error {
	delete(f.pods, name)
	return nil
}

type fakeStore struct {
	inserted []state.SandboxRecord
	updated  []string
	events   []state.SandboxEventRecord
}

func (f *fakeStore) InsertSandbox(_ context.Context, record state.SandboxRecord) error {
	f.inserted = append(f.inserted, record)
	return nil
}

func (f *fakeStore) UpdateSandboxState(_ context.Context, sandboxID string, stateValue string, _ string, _ int32, _ *int64) error {
	f.updated = append(f.updated, sandboxID+":"+stateValue)
	return nil
}

func (f *fakeStore) InsertSandboxEvent(_ context.Context, record state.SandboxEventRecord) error {
	f.events = append(f.events, record)
	return nil
}

type fakeEmitter struct {
	events []*sandboxv1.SandboxEvent
}

func (f *fakeEmitter) Emit(_ context.Context, event *sandboxv1.SandboxEvent, _ events.Envelope) error {
	f.events = append(f.events, event)
	return nil
}

func TestManagerCreateAndConcurrentLimit(t *testing.T) {
	pods := &fakePodController{}
	store := &fakeStore{}
	emitter := &fakeEmitter{}
	manager := NewManager(ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  1,
		Store:          store,
		Pods:           pods,
		Emitter:        emitter,
	})
	req := &sandboxv1.CreateSandboxRequest{
		TemplateName: "python3.12",
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: uuid.NewString(),
		},
	}
	entry, err := manager.Create(context.Background(), req)
	if err != nil {
		t.Fatalf("create sandbox: %v", err)
	}
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		current, getErr := manager.Get(entry.SandboxID)
		if getErr == nil && current.State == sandboxv1.SandboxState_SANDBOX_STATE_READY {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	current, err := manager.Get(entry.SandboxID)
	if err != nil {
		t.Fatalf("get sandbox: %v", err)
	}
	if current.State != sandboxv1.SandboxState_SANDBOX_STATE_READY {
		t.Fatalf("expected ready state, got %s", current.State.String())
	}
	if len(store.inserted) != 1 || len(store.events) == 0 || len(emitter.events) == 0 {
		t.Fatal("expected persistence and event emission")
	}
	if _, err := manager.Create(context.Background(), req); err != ErrConcurrentLimit {
		t.Fatalf("expected concurrent limit, got %v", err)
	}
}

func TestManagerMarkTerminatedDeletesPod(t *testing.T) {
	pods := &fakePodController{}
	manager := NewManager(ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  2,
		Store:          &fakeStore{},
		Pods:           pods,
		Emitter:        &fakeEmitter{},
	})
	req := &sandboxv1.CreateSandboxRequest{
		TemplateName: "python3.12",
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: uuid.NewString(),
		},
	}
	entry, err := manager.Create(context.Background(), req)
	if err != nil {
		t.Fatalf("create sandbox: %v", err)
	}
	if err := manager.MarkTerminated(context.Background(), entry.SandboxID, 0); err != nil {
		t.Fatalf("mark terminated: %v", err)
	}
	if manager.HasSandbox(entry.SandboxID) {
		t.Fatal("sandbox should be removed from manager")
	}
}

func TestStateNameJSONMarshalling(t *testing.T) {
	body, err := json.Marshal(map[string]string{"state": stateName(sandboxv1.SandboxState_SANDBOX_STATE_READY)})
	if err != nil {
		t.Fatalf("marshal state name: %v", err)
	}
	if string(body) != `{"state":"ready"}` {
		t.Fatalf("unexpected payload %s", string(body))
	}
}
