package launcher

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	v1 "k8s.io/api/core/v1"
)

type fakeStore struct {
	inserted  []state.RuntimeRecord
	taskPlans []state.TaskPlanRecord
	events    []state.RuntimeEventRecord
	runtime   state.RuntimeRecord
	getErr    error
	updatedTo string
	updateErr error
}

func (f *fakeStore) InsertRuntime(_ context.Context, record state.RuntimeRecord) error {
	f.inserted = append(f.inserted, record)
	return nil
}

func (f *fakeStore) GetRuntimeByExecutionID(context.Context, string) (state.RuntimeRecord, error) {
	return f.runtime, f.getErr
}

func (f *fakeStore) UpdateRuntimeState(_ context.Context, _ string, stateValue string, _ string) error {
	if f.updateErr != nil {
		return f.updateErr
	}
	f.updatedTo = stateValue
	return nil
}

func (f *fakeStore) InsertTaskPlanRecord(_ context.Context, record state.TaskPlanRecord) error {
	f.taskPlans = append(f.taskPlans, record)
	return nil
}

func (f *fakeStore) InsertRuntimeEvent(_ context.Context, event state.RuntimeEventRecord) error {
	f.events = append(f.events, event)
	return nil
}

type fakePodManager struct{ created *v1.Pod }

func (f *fakePodManager) CreatePod(_ context.Context, pod *v1.Pod) (*v1.Pod, error) {
	f.created = pod
	return pod, nil
}

type fakeSecretResolver struct{ err error }

func (f fakeSecretResolver) Resolve(context.Context, []string) ([]v1.VolumeProjection, []v1.EnvVar, error) {
	return nil, nil, f.err
}

type fakePresigner struct{}

func (fakePresigner) PresignAgentPackageURL(context.Context, string, time.Duration) (string, error) {
	return "https://example.invalid/package.tgz", nil
}

type fakePresignerError struct{}

func (fakePresignerError) PresignAgentPackageURL(context.Context, string, time.Duration) (string, error) {
	return "", errors.New("presign failed")
}

type fakeWarmPoolDispatcher struct {
	podName string
	ok      bool
}

func (f fakeWarmPoolDispatcher) Dispatch(string, string) (string, bool) { return f.podName, f.ok }

func TestLaunchCreatesPendingRuntimeThenRunningPod(t *testing.T) {
	store := &fakeStore{getErr: pgx.ErrNoRows}
	pods := &fakePodManager{}
	service := &Launcher{
		Namespace:  "platform-execution",
		PresignTTL: time.Hour,
		Store:      store,
		Pods:       pods,
		Presigner:  fakePresigner{},
	}
	info, warmStart, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		AgentRevision: "agent-v1",
		CorrelationContext: &runtimev1.CorrelationContext{
			ExecutionId: "exec-1",
			WorkspaceId: "ws-1",
		},
		ResourceLimits: &runtimev1.ResourceLimits{},
		TaskPlanJson:   `{"task":"plan"}`,
	})
	if err != nil {
		t.Fatalf("Launch returned error: %v", err)
	}
	if warmStart {
		t.Fatalf("expected cold launch")
	}
	if info.State != runtimev1.RuntimeState_RUNTIME_STATE_RUNNING {
		t.Fatalf("expected running state, got %v", info.State)
	}
	if len(store.inserted) != 1 || pods.created == nil || store.updatedTo != "running" {
		t.Fatalf("launch did not persist and create pod as expected")
	}
	if len(store.taskPlans) != 1 {
		t.Fatalf("expected task plan persistence")
	}
}

func TestLaunchRejectsDuplicateExecutionID(t *testing.T) {
	store := &fakeStore{runtime: state.RuntimeRecord{RuntimeID: uuid.New(), ExecutionID: "exec-1"}}
	service := &Launcher{Store: store}
	_, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		CorrelationContext: &runtimev1.CorrelationContext{ExecutionId: "exec-1", WorkspaceId: "ws-1"},
	})
	if !errors.Is(err, ErrAlreadyExists) {
		t.Fatalf("expected ErrAlreadyExists, got %v", err)
	}
}

func TestLaunchRejectsInvalidContract(t *testing.T) {
	service := &Launcher{Store: &fakeStore{}}

	if _, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{}); !errors.Is(err, ErrInvalidContract) {
		t.Fatalf("expected ErrInvalidContract, got %v", err)
	}
}

func TestLaunchUsesWarmPoolWithoutCreatingPod(t *testing.T) {
	store := &fakeStore{getErr: pgx.ErrNoRows}
	pods := &fakePodManager{}
	service := &Launcher{
		Namespace: "platform-execution",
		Store:     store,
		Pods:      pods,
		WarmPool:  fakeWarmPoolDispatcher{podName: "warm-pod-1", ok: true},
	}

	info, warmStart, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		AgentRevision: "agent-v1",
		CorrelationContext: &runtimev1.CorrelationContext{
			ExecutionId: "exec-1",
			WorkspaceId: "ws-1",
		},
	})
	if err != nil {
		t.Fatalf("Launch returned error: %v", err)
	}
	if !warmStart || info.PodName != "warm-pod-1" || pods.created != nil {
		t.Fatalf("unexpected warm pool launch result: warm=%v info=%+v created=%+v", warmStart, info, pods.created)
	}
}

func TestLaunchPropagatesSecretResolutionError(t *testing.T) {
	store := &fakeStore{getErr: pgx.ErrNoRows}
	service := &Launcher{
		Namespace: "platform-execution",
		Store:     store,
		Pods:      &fakePodManager{},
		Secrets:   fakeSecretResolver{err: errors.New("secret failure")},
	}

	if _, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		AgentRevision: "agent-v1",
		CorrelationContext: &runtimev1.CorrelationContext{
			ExecutionId: "exec-1",
			WorkspaceId: "ws-1",
		},
	}); err == nil {
		t.Fatalf("expected secret resolution error")
	}
}

func TestSecretResolverFuncResolveDelegates(t *testing.T) {
	called := false
	resolver := secretResolverFunc(func(context.Context, []string) ([]v1.VolumeProjection, []v1.EnvVar, error) {
		called = true
		return nil, nil, nil
	})

	if _, _, err := resolver.Resolve(context.Background(), []string{"secret-a"}); err != nil {
		t.Fatalf("Resolve returned error: %v", err)
	}
	if !called {
		t.Fatalf("expected delegated resolver to be called")
	}
}

func TestLaunchPropagatesOperationalErrors(t *testing.T) {
	store := &fakeStore{getErr: pgx.ErrNoRows}
	pods := &fakePodManager{}
	service := &Launcher{
		Namespace:  "platform-execution",
		Store:      store,
		Pods:       pods,
		Presigner:  fakePresignerError{},
		PresignTTL: time.Hour,
	}

	if _, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		AgentRevision: "agent-v1",
		CorrelationContext: &runtimev1.CorrelationContext{
			ExecutionId: "exec-1",
			WorkspaceId: "ws-1",
		},
	}); err == nil {
		t.Fatalf("expected presign error")
	}

	store = &fakeStore{getErr: pgx.ErrNoRows, updateErr: errors.New("update failed")}
	service = &Launcher{
		Namespace:  "platform-execution",
		Store:      store,
		Pods:       pods,
		Presigner:  fakePresigner{},
		PresignTTL: time.Hour,
	}
	if _, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		AgentRevision: "agent-v1",
		CorrelationContext: &runtimev1.CorrelationContext{
			ExecutionId: "exec-1",
			WorkspaceId: "ws-1",
		},
	}); err == nil {
		t.Fatalf("expected update error")
	}
}

func TestMustJSON(t *testing.T) {
	body := mustJSON(map[string]string{"hello": "world"})
	var decoded map[string]string
	if err := json.Unmarshal(body, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if decoded["hello"] != "world" {
		t.Fatalf("unexpected payload: %+v", decoded)
	}
}
