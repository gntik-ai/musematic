package reconciler

import (
	"context"
	"testing"

	"github.com/andrea-mucci/musematic/services/runtime-controller/internal/state"
	"github.com/google/uuid"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

type fakeRuntimeStore struct {
	runtimes  []state.RuntimeRecord
	updated   map[string]string
	listErr   error
	updateErr error
}

func (f *fakeRuntimeStore) ListActiveRuntimes(context.Context) ([]state.RuntimeRecord, error) {
	return f.runtimes, f.listErr
}

func (f *fakeRuntimeStore) UpdateRuntimeState(_ context.Context, executionID string, stateValue string, _ string) error {
	if f.updateErr != nil {
		return f.updateErr
	}
	if f.updated == nil {
		f.updated = map[string]string{}
	}
	f.updated[executionID] = stateValue
	return nil
}

func (f *fakeRuntimeStore) InsertRuntimeEvent(context.Context, state.RuntimeEventRecord) error {
	return nil
}

type fakePods struct {
	pods    []v1.Pod
	deleted []string
	listErr error
}

func (f *fakePods) ListPodsByLabel(context.Context, string) ([]v1.Pod, error) {
	return f.pods, f.listErr
}
func (f *fakePods) DeletePod(_ context.Context, name string, _ int64) error {
	f.deleted = append(f.deleted, name)
	return nil
}

func TestDetectDriftFindsOrphansMissingAndMismatches(t *testing.T) {
	store := &fakeRuntimeStore{runtimes: []state.RuntimeRecord{
		{RuntimeID: uuid.New(), ExecutionID: "exec-running", State: "running"},
		{RuntimeID: uuid.New(), ExecutionID: "exec-missing", State: "running"},
	}}
	pods := &fakePods{pods: []v1.Pod{
		{ObjectMeta: metav1.ObjectMeta{Name: "pod-running", Labels: map[string]string{"execution_id": "exec-running"}}, Status: v1.PodStatus{Phase: v1.PodFailed}},
		{ObjectMeta: metav1.ObjectMeta{Name: "orphan", Labels: map[string]string{"execution_id": "orphan"}}},
	}}
	report, err := DetectDrift(context.Background(), store, pods)
	if err != nil {
		t.Fatalf("DetectDrift returned error: %v", err)
	}
	if len(report.Orphans) != 1 || len(report.Missing) != 1 || len(report.Mismatches) != 1 {
		t.Fatalf("unexpected report: %+v", report)
	}
}

func TestDetectDriftPropagatesPodListError(t *testing.T) {
	store := &fakeRuntimeStore{runtimes: []state.RuntimeRecord{{RuntimeID: uuid.New(), ExecutionID: "exec-1", State: "running"}}}
	pods := &fakePods{listErr: context.DeadlineExceeded}
	if _, err := DetectDrift(context.Background(), store, pods); err == nil {
		t.Fatalf("expected pod list error")
	}
}
