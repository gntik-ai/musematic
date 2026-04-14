package executor

import (
	"context"
	"errors"
	"io"
	"testing"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	"k8s.io/client-go/rest"
)

type errorExecStore struct {
	updateErr error
}

func (errorExecStore) InsertSandbox(context.Context, state.SandboxRecord) error { return nil }

func (s errorExecStore) UpdateSandboxState(context.Context, string, string, string, int32, *int64) error {
	return s.updateErr
}

func (errorExecStore) InsertSandboxEvent(context.Context, state.SandboxEventRecord) error { return nil }

func waitReady(t *testing.T, manager *sandbox.Manager, sandboxID string) {
	t.Helper()

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		current, err := manager.Get(sandboxID)
		if err == nil && current.State == sandboxv1.SandboxState_SANDBOX_STATE_READY {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatal("sandbox did not reach ready state")
}

func newExecManager(t *testing.T, store sandbox.Store) (*sandbox.Manager, *execPodController, *sandbox.Entry) {
	t.Helper()

	pods := &execPodController{}
	manager := sandbox.NewManager(sandbox.ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  2,
		Store:          store,
		Pods:           pods,
		Emitter:        execEmitter{},
	})
	entry, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
		TemplateName: "python3.12",
		Correlation:  &sandboxv1.CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1"},
	})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	waitReady(t, manager, entry.SandboxID)
	current, err := manager.Get(entry.SandboxID)
	if err != nil {
		t.Fatalf("Get() error = %v", err)
	}
	return manager, pods, current
}

func TestExecuteErrorsForMissingSandboxAndInvalidState(t *testing.T) {
	manager := sandbox.NewManager(sandbox.ManagerConfig{Namespace: "platform-execution"})
	exec := New(manager, &execPodController{}, nil, 1024)
	if _, _, err := exec.Execute(context.Background(), "missing", `print("hello")`, 5); !errors.Is(err, sandbox.ErrSandboxNotFound) {
		t.Fatalf("Execute() error = %v, want %v", err, sandbox.ErrSandboxNotFound)
	}

	pods := &execPodController{}
	manager = sandbox.NewManager(sandbox.ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  1,
		Store:          execStore{},
		Pods:           pods,
		Emitter:        execEmitter{},
	})
	entry, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
		TemplateName: "python3.12",
		Correlation:  &sandboxv1.CorrelationContext{WorkspaceId: "ws-1", ExecutionId: "exec-1"},
	})
	if err != nil {
		t.Fatalf("Create() error = %v", err)
	}
	exec = New(manager, pods, nil, 1024)
	if _, _, err := exec.Execute(context.Background(), entry.SandboxID, `print("hello")`, 5); !errors.Is(err, sandbox.ErrInvalidState) {
		t.Fatalf("Execute() error = %v, want %v", err, sandbox.ErrInvalidState)
	}
}

func TestExecutePropagatesFinishAndExecErrors(t *testing.T) {
	t.Run("record step failure", func(t *testing.T) {
		expectedErr := errors.New("update boom")
		manager, pods, entry := newExecManager(t, errorExecStore{updateErr: expectedErr})
		exec := New(manager, pods, nil, 1024)
		exec.Exec = func(context.Context, *rest.Config, string, string, []string, io.Reader, io.Writer, io.Writer) error {
			return nil
		}
		if _, _, err := exec.Execute(context.Background(), entry.SandboxID, `print("hello")`, 5); !errors.Is(err, expectedErr) {
			t.Fatalf("Execute() error = %v, want %v", err, expectedErr)
		}
	})

	t.Run("plain exec error", func(t *testing.T) {
		manager, pods, entry := newExecManager(t, execStore{})
		expectedErr := errors.New("exec boom")
		exec := New(manager, pods, nil, 1024)
		exec.Exec = func(context.Context, *rest.Config, string, string, []string, io.Reader, io.Writer, io.Writer) error {
			return expectedErr
		}
		if _, _, err := exec.Execute(context.Background(), entry.SandboxID, `print("hello")`, 5); !errors.Is(err, expectedErr) {
			t.Fatalf("Execute() error = %v, want %v", err, expectedErr)
		}
	})
}
