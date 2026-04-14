package cleanup

import (
	"context"
	"errors"
	"testing"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/events"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	v1 "k8s.io/api/core/v1"
)

type idlePodController struct {
	pod     *v1.Pod
	deleted []string
}

func (c *idlePodController) CreatePod(_ context.Context, pod *v1.Pod) (*v1.Pod, error) {
	copy := pod.DeepCopy()
	copy.Status.Phase = v1.PodRunning
	c.pod = copy
	return copy, nil
}

func (c *idlePodController) GetPod(_ context.Context, _ string) (*v1.Pod, error) {
	if len(c.deleted) > 0 {
		return nil, context.Canceled
	}
	return c.pod.DeepCopy(), nil
}

func (c *idlePodController) ListPodsByLabel(context.Context, string) ([]v1.Pod, error) {
	return []v1.Pod{*c.pod.DeepCopy()}, nil
}

func (c *idlePodController) DeletePod(_ context.Context, podName string, _ int64) error {
	c.deleted = append(c.deleted, podName)
	return nil
}

type idleStore struct{}

func (idleStore) InsertSandbox(context.Context, state.SandboxRecord) error { return nil }
func (idleStore) UpdateSandboxState(context.Context, string, string, string, int32, *int64) error {
	return nil
}
func (idleStore) InsertSandboxEvent(context.Context, state.SandboxEventRecord) error { return nil }

type idleEmitter struct{}

func (idleEmitter) Emit(context.Context, *sandboxv1.SandboxEvent, events.Envelope) error { return nil }

func TestIdleScannerTerminatesExpiredSandboxes(t *testing.T) {
	t.Parallel()

	pods := &idlePodController{}
	manager := sandbox.NewManager(sandbox.ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  1,
		Store:          idleStore{},
		Pods:           pods,
		Emitter:        idleEmitter{},
	})
	entry, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
		TemplateName: "python3.12",
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
	})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		current, getErr := manager.Get(entry.SandboxID)
		if getErr == nil && current.State == sandboxv1.SandboxState_SANDBOX_STATE_READY {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() {
		done <- (&IdleScanner{Manager: manager, IdleTimeout: 20 * time.Millisecond, Interval: 10 * time.Millisecond}).Run(ctx)
	}()

	timeout := time.Now().Add(2 * time.Second)
	for time.Now().Before(timeout) {
		if !manager.HasSandbox(entry.SandboxID) {
			cancel()
			if err := <-done; err != context.Canceled {
				t.Fatalf("Run() error = %v", err)
			}
			if len(pods.deleted) == 0 {
				t.Fatal("expected sandbox pod deletion")
			}
			return
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatal("expected idle scanner to terminate sandbox")
}

func TestIdleScannerRunNilManager(t *testing.T) {
	t.Parallel()

	if err := (&IdleScanner{}).Run(context.Background()); err != nil {
		t.Fatalf("Run() error = %v", err)
	}
}

func TestIdleScannerRunStopsOnContextCancel(t *testing.T) {
	t.Parallel()

	manager := sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution", MaxConcurrent: 1})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	if err := (&IdleScanner{Manager: manager, IdleTimeout: time.Second, Interval: 10 * time.Millisecond}).Run(ctx); !errors.Is(err, context.Canceled) {
		t.Fatalf("Run() error = %v, want %v", err, context.Canceled)
	}
}
