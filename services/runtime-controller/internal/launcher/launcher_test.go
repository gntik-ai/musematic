package launcher

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	v1 "k8s.io/api/core/v1"
)

type fakeStore struct {
	inserted    []state.RuntimeRecord
	taskPlans   []state.TaskPlanRecord
	events      []state.RuntimeEventRecord
	runtime     state.RuntimeRecord
	getErr      error
	insertErr   error
	taskPlanErr error
	updatedTo   string
	updateErr   error
}

func (f *fakeStore) InsertRuntime(_ context.Context, record state.RuntimeRecord) error {
	if f.insertErr != nil {
		return f.insertErr
	}
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
	if f.taskPlanErr != nil {
		return f.taskPlanErr
	}
	f.taskPlans = append(f.taskPlans, record)
	return nil
}

func (f *fakeStore) InsertRuntimeEvent(_ context.Context, event state.RuntimeEventRecord) error {
	f.events = append(f.events, event)
	return nil
}

type fakePodManager struct {
	created    *v1.Pod
	createErr  error
	prepareErr error
	prepared   string
}

func (f *fakePodManager) CreatePod(_ context.Context, pod *v1.Pod) (*v1.Pod, error) {
	if f.createErr != nil {
		return nil, f.createErr
	}
	f.created = pod
	return pod, nil
}

func (f *fakePodManager) PrepareWarmPod(context.Context, string, *runtimev1.RuntimeContract) error {
	if f.prepareErr != nil {
		return f.prepareErr
	}
	f.prepared = "called"
	return nil
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
	err     error
}

func (f fakeWarmPoolDispatcher) Dispatch(context.Context, string, string, uuid.UUID) (string, bool, error) {
	return f.podName, f.ok, f.err
}

func TestLaunchCreatesRunningRuntimeAfterPodCreation(t *testing.T) {
	store := &fakeStore{getErr: pgx.ErrNoRows}
	pods := &fakePodManager{}
	service := &Launcher{
		Namespace:  "platform-execution",
		PresignTTL: time.Hour,
		Store:      store,
		Pods:       pods,
		Presigner:  fakePresigner{},
		Fanout:     events.NewFanoutRegistry(),
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
	if len(store.inserted) != 1 || pods.created == nil {
		t.Fatalf("launch did not persist and create pod as expected")
	}
	if store.updatedTo != "" {
		t.Fatalf("expected launch to insert the runtime directly in running state, got update %q", store.updatedTo)
	}
	if store.inserted[0].State != "running" || store.inserted[0].PodName == "" || store.inserted[0].LaunchedAt == nil {
		t.Fatalf("expected running runtime record with pod metadata, got %+v", store.inserted[0])
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
	if len(store.inserted) != 1 || store.inserted[0].PodName != "warm-pod-1" || store.inserted[0].LaunchedAt == nil {
		t.Fatalf("expected warm start to persist a running runtime, got %+v", store.inserted)
	}
}

func TestLaunchWarmPoolErrors(t *testing.T) {
	store := &fakeStore{getErr: pgx.ErrNoRows}
	service := &Launcher{
		Namespace: "platform-execution",
		Store:     store,
		Pods:      &fakePodManager{},
		WarmPool:  fakeWarmPoolDispatcher{err: errors.New("dispatch failed")},
	}
	info, warmStart, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		AgentRevision: "agent-v1",
		CorrelationContext: &runtimev1.CorrelationContext{
			ExecutionId: "exec-1",
			WorkspaceId: "ws-1",
		},
	})
	if err != nil {
		t.Fatalf("expected cold-start fallback, got error: %v", err)
	}
	if warmStart || info == nil {
		t.Fatalf("expected cold-start fallback response, got warm=%v info=%+v", warmStart, info)
	}

	service.WarmPool = fakeWarmPoolDispatcher{podName: "warm-pod-1", ok: true}
	service.Pods = &fakePodManager{prepareErr: errors.New("prepare failed")}
	if _, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		AgentRevision: "agent-v1",
		CorrelationContext: &runtimev1.CorrelationContext{
			ExecutionId: "exec-2",
			WorkspaceId: "ws-1",
		},
	}); err == nil {
		t.Fatalf("expected warm pod preparation error")
	}
	if len(store.inserted) != 1 {
		t.Fatalf("warm pod preparation failure should not persist a second runtime, got %d records", len(store.inserted))
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
	store := &fakeStore{getErr: errors.New("lookup failed")}
	service := &Launcher{Store: store}
	if _, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		CorrelationContext: &runtimev1.CorrelationContext{ExecutionId: "exec-1", WorkspaceId: "ws-1"},
	}); err == nil {
		t.Fatalf("expected lookup error")
	}

	store = &fakeStore{getErr: pgx.ErrNoRows, insertErr: errors.New("insert failed")}
	service = &Launcher{Store: store, Pods: &fakePodManager{}}
	if _, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		CorrelationContext: &runtimev1.CorrelationContext{ExecutionId: "exec-1", WorkspaceId: "ws-1"},
	}); err == nil {
		t.Fatalf("expected insert error")
	}

	store = &fakeStore{getErr: pgx.ErrNoRows, taskPlanErr: errors.New("task plan failed")}
	service = &Launcher{Store: store}
	if _, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		TaskPlanJson:       `{"task":"plan"}`,
		CorrelationContext: &runtimev1.CorrelationContext{ExecutionId: "exec-1", WorkspaceId: "ws-1"},
	}); err == nil {
		t.Fatalf("expected task plan error")
	}

	store = &fakeStore{getErr: pgx.ErrNoRows}
	service = &Launcher{Store: store, Pods: &fakePodManager{createErr: errors.New("create failed")}}
	if _, _, err := service.Launch(context.Background(), &runtimev1.RuntimeContract{
		CorrelationContext: &runtimev1.CorrelationContext{ExecutionId: "exec-1", WorkspaceId: "ws-1"},
	}); err == nil {
		t.Fatalf("expected create pod error")
	}
	if len(store.inserted) != 0 {
		t.Fatalf("create pod failure should not persist a runtime, got %+v", store.inserted)
	}

	store = &fakeStore{getErr: pgx.ErrNoRows}
	pods := &fakePodManager{}
	service = &Launcher{
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

}

func TestMustJSON(t *testing.T) {
	if mustJSON(nil) != nil {
		t.Fatalf("expected nil JSON for nil value")
	}
	body := mustJSON(map[string]string{"hello": "world"})
	var decoded map[string]string
	if err := json.Unmarshal(body, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if decoded["hello"] != "world" {
		t.Fatalf("unexpected payload: %+v", decoded)
	}
}
