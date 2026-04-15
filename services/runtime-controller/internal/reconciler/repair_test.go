package reconciler

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/events"
	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/andrea-mucci/musematic/services/runtime-controller/pkg/metrics"
	"github.com/google/uuid"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

type recordingStore struct {
	fakeRuntimeStore
	events []state.RuntimeEventRecord
}

func (r *recordingStore) InsertRuntimeEvent(_ context.Context, event state.RuntimeEventRecord) error {
	r.events = append(r.events, event)
	return nil
}

func TestApplyRepairsDeletesOrphansAndPublishesEvents(t *testing.T) {
	missing := state.RuntimeRecord{RuntimeID: uuid.New(), ExecutionID: "exec-missing", WorkspaceID: "ws-1"}
	mismatch := state.RuntimeRecord{RuntimeID: uuid.New(), ExecutionID: "exec-failed", WorkspaceID: "ws-1"}
	store := &recordingStore{fakeRuntimeStore: fakeRuntimeStore{}}
	pods := &fakePods{}
	fanout := events.NewFanoutRegistry()
	missingCh, missingUnsub := fanout.Subscribe("exec-missing")
	defer missingUnsub()
	failedCh, failedUnsub := fanout.Subscribe("exec-failed")
	defer failedUnsub()

	report := DriftReport{
		Orphans: []v1.Pod{{}},
		Missing: []DriftItem{{Runtime: missing, Reason: "pod_disappeared"}},
		Mismatches: []DriftItem{{
			Runtime: mismatch,
			Reason:  "failed",
		}},
	}

	if err := ApplyRepairs(context.Background(), report, store, pods, store, nil, fanout, nil); err != nil {
		t.Fatalf("ApplyRepairs returned error: %v", err)
	}
	if len(pods.deleted) != 1 {
		t.Fatalf("expected orphan pod deletion")
	}
	if got := store.updated["exec-missing"]; got != "failed" {
		t.Fatalf("unexpected missing runtime state: %q", got)
	}
	if got := store.updated["exec-failed"]; got != "failed" {
		t.Fatalf("unexpected mismatch runtime state: %q", got)
	}
	if len(store.events) != 2 {
		t.Fatalf("expected two persisted repair events, got %d", len(store.events))
	}
	if event := <-missingCh; event.EventType != runtimev1.RuntimeEventType_RUNTIME_EVENT_DRIFT_DETECTED {
		t.Fatalf("unexpected missing fanout event: %+v", event)
	}
	if event := <-failedCh; event.NewState != runtimev1.RuntimeState_RUNTIME_STATE_FAILED {
		t.Fatalf("unexpected mismatch fanout event: %+v", event)
	}
}

func TestApplyRepairsHandlesRunningMismatchAndUpdateError(t *testing.T) {
	mismatch := state.RuntimeRecord{RuntimeID: uuid.New(), ExecutionID: "exec-running", WorkspaceID: "ws-1"}
	store := &recordingStore{fakeRuntimeStore: fakeRuntimeStore{}}
	report := DriftReport{Mismatches: []DriftItem{{Runtime: mismatch, Reason: "running"}}}
	if err := ApplyRepairs(context.Background(), report, store, &fakePods{}, store, nil, nil, nil); err != nil {
		t.Fatalf("ApplyRepairs returned error: %v", err)
	}
	if got := store.updated["exec-running"]; got != "running" {
		t.Fatalf("unexpected mismatch repair state: %q", got)
	}

	store = &recordingStore{fakeRuntimeStore: fakeRuntimeStore{updateErr: errors.New("update failed")}}
	if err := ApplyRepairs(context.Background(), DriftReport{Missing: []DriftItem{{Runtime: mismatch}}}, store, &fakePods{}, store, nil, nil, nil); err == nil {
		t.Fatalf("expected update error")
	}
}

func TestStateFromPodPhase(t *testing.T) {
	if got := stateFromPodPhase(v1.PodPending); got != "pending" {
		t.Fatalf("unexpected pending mapping: %s", got)
	}
	if got := stateFromPodPhase(v1.PodRunning); got != "running" {
		t.Fatalf("unexpected running mapping: %s", got)
	}
	if got := stateFromPodPhase(v1.PodSucceeded); got != "stopped" {
		t.Fatalf("unexpected succeeded mapping: %s", got)
	}
	if got := stateFromPodPhase(v1.PodFailed); got != "failed" {
		t.Fatalf("unexpected failed mapping: %s", got)
	}
	if got := stateFromPodPhase(v1.PodUnknown); got != "" {
		t.Fatalf("unexpected unknown mapping: %s", got)
	}
}

func TestReconcilerRunOnceAndRun(t *testing.T) {
	store := &recordingStore{fakeRuntimeStore: fakeRuntimeStore{
		runtimes: []state.RuntimeRecord{{RuntimeID: uuid.New(), ExecutionID: "exec-1", State: "running"}},
	}}
	pods := &fakePods{pods: []v1.Pod{{ObjectMeta: metav1.ObjectMeta{Name: "orphan", Labels: map[string]string{"execution_id": "orphan"}}}}}
	reconciler := &Reconciler{
		Interval: time.Millisecond,
		Store:    store,
		Pods:     pods,
		Metrics:  metrics.NewRegistry(),
	}

	if err := reconciler.RunOnce(context.Background()); err != nil {
		t.Fatalf("RunOnce returned error: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := reconciler.Run(ctx); !errors.Is(err, context.Canceled) {
		t.Fatalf("expected canceled context, got %v", err)
	}
}

func TestRunOncePropagatesDetectDriftErrors(t *testing.T) {
	reconciler := &Reconciler{
		Store: &recordingStore{fakeRuntimeStore: fakeRuntimeStore{}},
		Pods:  &fakePods{},
	}
	reconciler.Store.(*recordingStore).listErr = errors.New("list failed")
	if err := reconciler.RunOnce(context.Background()); err == nil {
		t.Fatalf("expected detect drift error")
	}
}
