package cleanup

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

type orphanPodsStub struct {
	pods    []v1.Pod
	deleted []string
	listErr error
	delErr  error
}

func (s *orphanPodsStub) ListPodsByLabel(context.Context, string) ([]v1.Pod, error) {
	return s.pods, s.listErr
}

func (s *orphanPodsStub) DeletePod(_ context.Context, podName string, _ int64) error {
	if s.delErr != nil {
		return s.delErr
	}
	s.deleted = append(s.deleted, podName)
	return nil
}

func TestOrphanScannerDeletesUnknownPods(t *testing.T) {
	t.Parallel()

	pods := &orphanPodsStub{
		pods: []v1.Pod{{
			ObjectMeta: metav1.ObjectMeta{
				Name:   "sandbox-orphan",
				Labels: map[string]string{"sandbox_id": "missing"},
			},
		}},
	}
	scanner := &OrphanScanner{
		Pods:     pods,
		Manager:  sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution", MaxConcurrent: 1}),
		Interval: 10 * time.Millisecond,
	}

	if err := scanner.scan(context.Background()); err != nil {
		t.Fatalf("scan() error = %v", err)
	}
	if len(pods.deleted) != 1 || pods.deleted[0] != "sandbox-orphan" {
		t.Fatalf("unexpected deleted pods: %v", pods.deleted)
	}
}

func TestOrphanScannerRunNilDependencies(t *testing.T) {
	t.Parallel()

	if err := (&OrphanScanner{}).Run(context.Background()); err != nil {
		t.Fatalf("Run() error = %v", err)
	}
}

func TestOrphanScannerRunStopsOnContextCancel(t *testing.T) {
	t.Parallel()

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	scanner := &OrphanScanner{
		Pods:     &orphanPodsStub{},
		Manager:  sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution", MaxConcurrent: 1}),
		Interval: 10 * time.Millisecond,
	}
	if err := scanner.Run(ctx); !errors.Is(err, context.Canceled) {
		t.Fatalf("Run() error = %v, want %v", err, context.Canceled)
	}
}

func TestOrphanScannerScanPropagatesErrorsAndSkipsManagedPods(t *testing.T) {
	t.Parallel()

	expectedErr := errors.New("delete boom")
	pods := &orphanPodsStub{
		pods: []v1.Pod{
			{ObjectMeta: metav1.ObjectMeta{Name: "sandbox-missing-label"}},
			{ObjectMeta: metav1.ObjectMeta{Name: "sandbox-orphan", Labels: map[string]string{"sandbox_id": "missing"}}},
		},
		delErr: expectedErr,
	}
	scanner := &OrphanScanner{
		Pods:     pods,
		Manager:  sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution", MaxConcurrent: 1}),
		Interval: 10 * time.Millisecond,
	}
	if err := scanner.scan(context.Background()); !errors.Is(err, expectedErr) {
		t.Fatalf("scan() error = %v, want %v", err, expectedErr)
	}
	if len(pods.deleted) != 0 {
		t.Fatalf("expected delete to stop on error before recording deletions, got %v", pods.deleted)
	}
}

func TestOrphanScannerScanPropagatesListError(t *testing.T) {
	t.Parallel()

	expectedErr := errors.New("list boom")
	scanner := &OrphanScanner{
		Pods:     &orphanPodsStub{listErr: expectedErr},
		Manager:  sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution", MaxConcurrent: 1}),
		Interval: 10 * time.Millisecond,
	}
	if err := scanner.scan(context.Background()); !errors.Is(err, expectedErr) {
		t.Fatalf("scan() error = %v, want %v", err, expectedErr)
	}
}

func TestOrphanScannerRunReturnsInitialScanError(t *testing.T) {
	t.Parallel()

	expectedErr := errors.New("scan boom")
	scanner := &OrphanScanner{
		Pods:     &orphanPodsStub{listErr: expectedErr},
		Manager:  sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution", MaxConcurrent: 1}),
		Interval: 10 * time.Millisecond,
	}
	if err := scanner.Run(context.Background()); !errors.Is(err, expectedErr) {
		t.Fatalf("Run() error = %v, want %v", err, expectedErr)
	}
}
