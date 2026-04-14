package sandbox

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/events"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	"github.com/google/uuid"
	v1 "k8s.io/api/core/v1"
)

type trackingPodController struct {
	pods         map[string]*v1.Pod
	createErr    error
	getErr       error
	deleteErr    error
	lastGrace    int64
	keepOnDelete bool
}

func (c *trackingPodController) CreatePod(_ context.Context, pod *v1.Pod) (*v1.Pod, error) {
	if c.createErr != nil {
		return nil, c.createErr
	}
	if c.pods == nil {
		c.pods = map[string]*v1.Pod{}
	}
	copy := pod.DeepCopy()
	copy.Status.Phase = v1.PodRunning
	c.pods[pod.Name] = copy
	return copy, nil
}

func (c *trackingPodController) GetPod(_ context.Context, name string) (*v1.Pod, error) {
	if c.getErr != nil {
		return nil, c.getErr
	}
	if pod, ok := c.pods[name]; ok {
		return pod.DeepCopy(), nil
	}
	return nil, context.Canceled
}

func (c *trackingPodController) ListPodsByLabel(context.Context, string) ([]v1.Pod, error) {
	items := make([]v1.Pod, 0, len(c.pods))
	for _, pod := range c.pods {
		items = append(items, *pod.DeepCopy())
	}
	return items, nil
}

func (c *trackingPodController) DeletePod(_ context.Context, name string, gracePeriod int64) error {
	if c.deleteErr != nil {
		return c.deleteErr
	}
	c.lastGrace = gracePeriod
	if !c.keepOnDelete {
		delete(c.pods, name)
	}
	return nil
}

type errorStore struct {
	insertErr error
	updateErr error
	eventErr  error
	updates   []string
}

func (s *errorStore) InsertSandbox(context.Context, state.SandboxRecord) error { return s.insertErr }

func (s *errorStore) UpdateSandboxState(_ context.Context, sandboxID string, stateValue string, _ string, _ int32, _ *int64) error {
	if s.updateErr != nil {
		return s.updateErr
	}
	s.updates = append(s.updates, sandboxID+":"+stateValue)
	return nil
}

func (s *errorStore) InsertSandboxEvent(context.Context, state.SandboxEventRecord) error {
	return s.eventErr
}

type errorEmitter struct {
	err error
}

func (e *errorEmitter) Emit(context.Context, *sandboxv1.SandboxEvent, events.Envelope) error {
	return e.err
}

func newManagerWithEntry(t *testing.T, stateValue sandboxv1.SandboxState, store Store, pods PodController, emitter EventEmitter) (*Manager, *Entry) {
	t.Helper()

	if pods == nil {
		pods = &trackingPodController{pods: map[string]*v1.Pod{}}
	}
	manager := NewManager(ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  2,
		Store:          store,
		Pods:           pods,
		Emitter:        emitter,
	})
	entry := &Entry{
		SandboxID:      uuid.NewString(),
		ExecutionID:    "exec-1",
		WorkspaceID:    "ws-1",
		Template:       "python3.12",
		State:          stateValue,
		PodName:        "sandbox-1",
		PodNamespace:   "platform-execution",
		CreatedAt:      time.Now().UTC(),
		LastActivityAt: time.Now().Add(-time.Minute).UTC(),
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
	}
	manager.sandboxes[entry.SandboxID] = entry
	if typedPods, ok := pods.(*trackingPodController); ok {
		if typedPods.pods == nil {
			typedPods.pods = map[string]*v1.Pod{}
		}
		typedPods.pods[entry.PodName] = &v1.Pod{Status: v1.PodStatus{Phase: v1.PodRunning}}
	}
	return manager, entry
}

func TestManagerCreateValidationAndCleanup(t *testing.T) {
	t.Parallel()

	t.Run("unknown template", func(t *testing.T) {
		manager := NewManager(ManagerConfig{Namespace: "platform-execution", MaxConcurrent: 1, Pods: &trackingPodController{}})
		_, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
			TemplateName: "missing",
			Correlation:  &sandboxv1.CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1"},
		})
		if !errors.Is(err, ErrTemplateNotFound) {
			t.Fatalf("Create() error = %v, want %v", err, ErrTemplateNotFound)
		}
	})

	t.Run("missing correlation", func(t *testing.T) {
		manager := NewManager(ManagerConfig{Namespace: "platform-execution", MaxConcurrent: 1, Pods: &trackingPodController{}})
		_, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{TemplateName: "python3.12"})
		if err == nil || !strings.Contains(err.Error(), "missing correlation context") {
			t.Fatalf("Create() error = %v", err)
		}
	})

	t.Run("pod create failure cleans sandbox", func(t *testing.T) {
		manager := NewManager(ManagerConfig{
			Namespace:     "platform-execution",
			MaxConcurrent: 1,
			Pods:          &trackingPodController{createErr: errors.New("create boom")},
		})
		_, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
			TemplateName: "python3.12",
			Correlation:  &sandboxv1.CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1"},
		})
		if err == nil {
			t.Fatal("expected Create() to fail")
		}
		if len(manager.List()) != 0 {
			t.Fatalf("expected cleanup after pod creation failure, got %d sandboxes", len(manager.List()))
		}
	})

	t.Run("store insert failure cleans sandbox", func(t *testing.T) {
		manager := NewManager(ManagerConfig{
			Namespace:     "platform-execution",
			MaxConcurrent: 1,
			Store:         &errorStore{insertErr: errors.New("insert boom")},
			Pods:          &trackingPodController{},
		})
		_, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
			TemplateName: "python3.12",
			Correlation:  &sandboxv1.CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1"},
		})
		if err == nil {
			t.Fatal("expected Create() to fail")
		}
		if len(manager.List()) != 0 {
			t.Fatalf("expected cleanup after store failure, got %d sandboxes", len(manager.List()))
		}
	})
}

func TestManagerListReturnsCopiesAndRecordStepUpdatesState(t *testing.T) {
	t.Parallel()

	store := &errorStore{}
	manager, entry := newManagerWithEntry(t, sandboxv1.SandboxState_SANDBOX_STATE_READY, store, &trackingPodController{}, &errorEmitter{})

	items := manager.List()
	if len(items) != 1 {
		t.Fatalf("List() returned %d items", len(items))
	}
	items[0].SandboxID = "mutated"
	got, err := manager.Get(entry.SandboxID)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if got.SandboxID != entry.SandboxID {
		t.Fatalf("expected List() to return copies, got %+v", got)
	}

	before := got.LastActivityAt
	stepNum, err := manager.RecordStep(entry.SandboxID, 250*time.Millisecond)
	if err != nil {
		t.Fatalf("RecordStep() error = %v", err)
	}
	updated, err := manager.Get(entry.SandboxID)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if stepNum != 1 || updated.TotalSteps != 1 || updated.TotalDurationMS != 250 {
		t.Fatalf("unexpected updated entry %+v", updated)
	}
	if !updated.LastActivityAt.After(before) {
		t.Fatalf("expected LastActivityAt to advance, before=%v after=%v", before, updated.LastActivityAt)
	}
	if len(store.updates) != 1 || !strings.Contains(store.updates[0], ":ready") {
		t.Fatalf("unexpected store updates %v", store.updates)
	}
}

func TestManagerRecordStepErrors(t *testing.T) {
	t.Parallel()

	manager := NewManager(ManagerConfig{Namespace: "platform-execution", MaxConcurrent: 1})
	if _, err := manager.RecordStep("missing", time.Second); !errors.Is(err, ErrSandboxNotFound) {
		t.Fatalf("RecordStep() error = %v, want %v", err, ErrSandboxNotFound)
	}

	store := &errorStore{updateErr: errors.New("update boom")}
	manager, entry := newManagerWithEntry(t, sandboxv1.SandboxState_SANDBOX_STATE_READY, store, &trackingPodController{}, &errorEmitter{})
	if _, err := manager.RecordStep(entry.SandboxID, time.Second); !errors.Is(err, store.updateErr) {
		t.Fatalf("RecordStep() error = %v, want %v", err, store.updateErr)
	}
}

func TestTransitionLifecycleAndHelpers(t *testing.T) {
	t.Parallel()

	manager, entry := newManagerWithEntry(t, sandboxv1.SandboxState_SANDBOX_STATE_READY, &errorStore{}, &trackingPodController{}, &errorEmitter{})

	if err := manager.Transition(context.Background(), entry.SandboxID, sandboxv1.SandboxState_SANDBOX_STATE_CREATING, sandboxv1.SandboxState_SANDBOX_STATE_READY, ""); !errors.Is(err, ErrInvalidState) {
		t.Fatalf("Transition() mismatch error = %v", err)
	}
	if err := manager.Transition(context.Background(), entry.SandboxID, sandboxv1.SandboxState_SANDBOX_STATE_READY, sandboxv1.SandboxState_SANDBOX_STATE_CREATING, ""); !errors.Is(err, ErrInvalidState) {
		t.Fatalf("Transition() invalid transition error = %v", err)
	}
	if err := manager.MarkFailed(context.Background(), entry.SandboxID, "boom"); err != nil {
		t.Fatalf("MarkFailed() error = %v", err)
	}
	failed, err := manager.Get(entry.SandboxID)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if failed.State != sandboxv1.SandboxState_SANDBOX_STATE_FAILED || failed.FailureReason != "boom" {
		t.Fatalf("unexpected failed entry %+v", failed)
	}
	if stateName(sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED) != "creating" {
		t.Fatalf("unexpected default state name %q", stateName(sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED))
	}
	if eventTypeForState(sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED) != sandboxv1.SandboxEventType_SANDBOX_EVENT_CREATED {
		t.Fatalf("unexpected default event type %s", eventTypeForState(sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED))
	}
	if eventNameForState(sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED) != "sandbox.created" {
		t.Fatalf("unexpected default event name %q", eventNameForState(sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED))
	}
	if !validTransition(sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED, sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED) {
		t.Fatal("expected completed -> terminated transition to be valid")
	}
}

func TestTransitionPropagatesStoreAndEmitterErrors(t *testing.T) {
	t.Parallel()

	store := &errorStore{updateErr: errors.New("update boom")}
	manager, entry := newManagerWithEntry(t, sandboxv1.SandboxState_SANDBOX_STATE_READY, store, &trackingPodController{}, &errorEmitter{})
	if err := manager.Transition(context.Background(), entry.SandboxID, sandboxv1.SandboxState_SANDBOX_STATE_READY, sandboxv1.SandboxState_SANDBOX_STATE_EXECUTING, ""); !errors.Is(err, store.updateErr) {
		t.Fatalf("Transition() error = %v, want %v", err, store.updateErr)
	}

	expectedErr := errors.New("emit boom")
	manager, entry = newManagerWithEntry(t, sandboxv1.SandboxState_SANDBOX_STATE_READY, &errorStore{}, &trackingPodController{}, &errorEmitter{err: expectedErr})
	if err := manager.Transition(context.Background(), entry.SandboxID, sandboxv1.SandboxState_SANDBOX_STATE_READY, sandboxv1.SandboxState_SANDBOX_STATE_EXECUTING, ""); !errors.Is(err, expectedErr) {
		t.Fatalf("Transition() error = %v, want %v", err, expectedErr)
	}
	if err := manager.emitState(context.Background(), nil, sandboxv1.SandboxEventType_SANDBOX_EVENT_CREATED, "sandbox.created"); err != nil {
		t.Fatalf("emitState(nil) error = %v", err)
	}
}

func TestMarkTerminatedEdgeCases(t *testing.T) {
	t.Parallel()

	t.Run("delete error", func(t *testing.T) {
		pods := &trackingPodController{deleteErr: errors.New("delete boom")}
		manager, entry := newManagerWithEntry(t, sandboxv1.SandboxState_SANDBOX_STATE_READY, &errorStore{}, pods, &errorEmitter{})
		if err := manager.MarkTerminated(context.Background(), entry.SandboxID, 5); !errors.Is(err, pods.deleteErr) {
			t.Fatalf("MarkTerminated() error = %v, want %v", err, pods.deleteErr)
		}
	})

	t.Run("negative grace period is clamped", func(t *testing.T) {
		pods := &trackingPodController{}
		manager, entry := newManagerWithEntry(t, sandboxv1.SandboxState_SANDBOX_STATE_READY, &errorStore{}, pods, &errorEmitter{})
		if err := manager.MarkTerminated(context.Background(), entry.SandboxID, -1); err != nil {
			t.Fatalf("MarkTerminated() error = %v", err)
		}
		if pods.lastGrace != 0 {
			t.Fatalf("expected grace period to clamp to 0, got %d", pods.lastGrace)
		}
		if manager.HasSandbox(entry.SandboxID) {
			t.Fatal("expected sandbox to be removed after termination")
		}
	})

	t.Run("context timeout still updates state", func(t *testing.T) {
		pods := &trackingPodController{keepOnDelete: true}
		manager, entry := newManagerWithEntry(t, sandboxv1.SandboxState_SANDBOX_STATE_READY, &errorStore{}, pods, &errorEmitter{})
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Millisecond)
		defer cancel()

		if err := manager.MarkTerminated(ctx, entry.SandboxID, 1); err != nil {
			t.Fatalf("MarkTerminated() error = %v", err)
		}
		if manager.HasSandbox(entry.SandboxID) {
			t.Fatal("expected sandbox removal even when pod polling times out")
		}
	})
}

func TestMonitorPodFailureAndTransitionMatrix(t *testing.T) {
	t.Parallel()

	pods := &trackingPodController{pods: map[string]*v1.Pod{}}
	manager, entry := newManagerWithEntry(t, sandboxv1.SandboxState_SANDBOX_STATE_CREATING, &errorStore{}, pods, &errorEmitter{})
	pods.pods[entry.PodName] = &v1.Pod{Status: v1.PodStatus{Phase: v1.PodFailed}}

	manager.monitorPod(context.Background(), entry.SandboxID)

	failed, err := manager.Get(entry.SandboxID)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if failed.State != sandboxv1.SandboxState_SANDBOX_STATE_FAILED {
		t.Fatalf("expected monitorPod() to mark sandbox failed, got %s", failed.State)
	}

	cases := []struct {
		from sandboxv1.SandboxState
		to   sandboxv1.SandboxState
		want bool
	}{
		{from: sandboxv1.SandboxState_SANDBOX_STATE_READY, to: sandboxv1.SandboxState_SANDBOX_STATE_FAILED, want: true},
		{from: sandboxv1.SandboxState_SANDBOX_STATE_READY, to: sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED, want: true},
		{from: sandboxv1.SandboxState_SANDBOX_STATE_FAILED, to: sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED, want: true},
		{from: sandboxv1.SandboxState_SANDBOX_STATE_UNSPECIFIED, to: sandboxv1.SandboxState_SANDBOX_STATE_CREATING, want: true},
		{from: sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED, to: sandboxv1.SandboxState_SANDBOX_STATE_READY, want: false},
	}
	for _, tc := range cases {
		if got := validTransition(tc.from, tc.to); got != tc.want {
			t.Fatalf("validTransition(%s, %s) = %v, want %v", tc.from, tc.to, got, tc.want)
		}
	}

	if eventTypeForState(sandboxv1.SandboxState_SANDBOX_STATE_FAILED) != sandboxv1.SandboxEventType_SANDBOX_EVENT_FAILED {
		t.Fatalf("unexpected failed event type %s", eventTypeForState(sandboxv1.SandboxState_SANDBOX_STATE_FAILED))
	}
	if eventTypeForState(sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED) != sandboxv1.SandboxEventType_SANDBOX_EVENT_COMPLETED {
		t.Fatalf("unexpected completed event type %s", eventTypeForState(sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED))
	}
	if eventTypeForState(sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED) != sandboxv1.SandboxEventType_SANDBOX_EVENT_TERMINATED {
		t.Fatalf("unexpected terminated event type %s", eventTypeForState(sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED))
	}
	if eventNameForState(sandboxv1.SandboxState_SANDBOX_STATE_FAILED) != "sandbox.failed" {
		t.Fatalf("unexpected failed event name %q", eventNameForState(sandboxv1.SandboxState_SANDBOX_STATE_FAILED))
	}
	if eventNameForState(sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED) != "sandbox.completed" {
		t.Fatalf("unexpected completed event name %q", eventNameForState(sandboxv1.SandboxState_SANDBOX_STATE_COMPLETED))
	}
	if eventNameForState(sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED) != "sandbox.terminated" {
		t.Fatalf("unexpected terminated event name %q", eventNameForState(sandboxv1.SandboxState_SANDBOX_STATE_TERMINATED))
	}
}

func TestMonitorPodReadyInvokesCallbackAndCopyDeepCopies(t *testing.T) {
	t.Parallel()

	pods := &trackingPodController{pods: map[string]*v1.Pod{}}
	readyCount := 0
	manager := NewManager(ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  2,
		Store:          &errorStore{},
		Pods:           pods,
		Emitter:        &errorEmitter{},
		ReadyCallback: func(Entry) {
			readyCount++
		},
	})
	entry := &Entry{
		SandboxID:      uuid.NewString(),
		ExecutionID:    "exec-1",
		WorkspaceID:    "ws-1",
		Template:       "python3.12",
		State:          sandboxv1.SandboxState_SANDBOX_STATE_CREATING,
		PodName:        "sandbox-1",
		PodNamespace:   "platform-execution",
		ResourceLimits: &sandboxv1.ResourceLimits{CpuRequest: "250m"},
		Correlation:    &sandboxv1.CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1"},
	}
	manager.sandboxes[entry.SandboxID] = entry
	pods.pods[entry.PodName] = &v1.Pod{Status: v1.PodStatus{Phase: v1.PodRunning}}

	manager.monitorPod(context.Background(), entry.SandboxID)

	ready, err := manager.Get(entry.SandboxID)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	if ready.State != sandboxv1.SandboxState_SANDBOX_STATE_READY || readyCount != 1 {
		t.Fatalf("unexpected ready state=%s readyCount=%d", ready.State, readyCount)
	}

	copy := ready.Copy()
	copy.ResourceLimits.CpuRequest = "500m"
	copy.Correlation.WorkspaceId = "ws-2"
	if ready.ResourceLimits.CpuRequest != "250m" || ready.Correlation.WorkspaceId != "ws-1" {
		t.Fatalf("expected Copy() to deep copy nested values, got %+v", ready)
	}
	if (*Entry)(nil).Copy() != nil {
		t.Fatal("expected nil Copy() receiver to return nil")
	}
}
