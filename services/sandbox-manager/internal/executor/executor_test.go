package executor

import (
	"context"
	"io"
	"testing"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/events"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/state"
	v1 "k8s.io/api/core/v1"
	"k8s.io/client-go/rest"
)

type execPodController struct {
	pod *v1.Pod
}

func (e *execPodController) CreatePod(_ context.Context, pod *v1.Pod) (*v1.Pod, error) {
	copy := pod.DeepCopy()
	copy.Status.Phase = v1.PodRunning
	e.pod = copy
	return copy, nil
}

func (e *execPodController) GetPod(_ context.Context, _ string) (*v1.Pod, error) {
	return e.pod.DeepCopy(), nil
}

func (e *execPodController) ListPodsByLabel(_ context.Context, _ string) ([]v1.Pod, error) {
	return []v1.Pod{*e.pod.DeepCopy()}, nil
}

func (e *execPodController) DeletePod(_ context.Context, _ string, _ int64) error { return nil }

type execStore struct{}

func (execStore) InsertSandbox(context.Context, state.SandboxRecord) error { return nil }
func (execStore) UpdateSandboxState(context.Context, string, string, string, int32, *int64) error {
	return nil
}
func (execStore) InsertSandboxEvent(context.Context, state.SandboxEventRecord) error { return nil }

type execEmitter struct{}

func (execEmitter) Emit(context.Context, *sandboxv1.SandboxEvent, events.Envelope) error { return nil }

func TestExecuteStep(t *testing.T) {
	pods := &execPodController{}
	manager := sandbox.NewManager(sandbox.ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  2,
		Store:          execStore{},
		Pods:           pods,
		Emitter:        execEmitter{},
	})
	entry, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
		TemplateName: "python3.12",
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
	})
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
	exec := New(manager, pods, nil, 1024)
	exec.Exec = func(_ context.Context, _ *rest.Config, _, _ string, _ []string, _ io.Reader, stdout io.Writer, _ io.Writer) error {
		_, _ = stdout.Write([]byte("hello\n"))
		return nil
	}
	result, stepNum, err := exec.Execute(context.Background(), entry.SandboxID, `print("hello")`, 5)
	if err != nil {
		t.Fatalf("execute step: %v", err)
	}
	if result.Stdout != "hello\n" || result.ExitCode != 0 {
		t.Fatalf("unexpected result: %#v", result)
	}
	if stepNum != 1 {
		t.Fatalf("expected first step number, got %d", stepNum)
	}
}

func TestExecuteCodeAsReasoningReturnsStructuredOutput(t *testing.T) {
	pods := &execPodController{}
	manager := sandbox.NewManager(sandbox.ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  2,
		Store:          execStore{},
		Pods:           pods,
		Emitter:        execEmitter{},
	})
	entry, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
		TemplateName: "code-as-reasoning",
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
	})
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

	exec := New(manager, pods, nil, 1024)
	exec.Exec = func(_ context.Context, _ *rest.Config, _, _ string, _ []string, _ io.Reader, stdout io.Writer, _ io.Writer) error {
		_, _ = stdout.Write([]byte(`{"result":"42","error":"","exit_code":0}`))
		return nil
	}

	result, _, err := exec.Execute(context.Background(), entry.SandboxID, `print(42)`, 5)
	if err != nil {
		t.Fatalf("execute step: %v", err)
	}
	if result.StructuredOutput == "" {
		t.Fatal("expected structured output to be returned")
	}
	if result.Stdout != "" {
		t.Fatalf("expected stdout to be cleared when structured output is detected, got %q", result.Stdout)
	}
}

func TestExecuteStepMarksTimeout(t *testing.T) {
	pods := &execPodController{}
	manager := sandbox.NewManager(sandbox.ManagerConfig{
		Namespace:      "platform-execution",
		DefaultTimeout: 30 * time.Second,
		MaxTimeout:     300 * time.Second,
		MaxConcurrent:  2,
		Store:          execStore{},
		Pods:           pods,
		Emitter:        execEmitter{},
	})
	entry, err := manager.Create(context.Background(), &sandboxv1.CreateSandboxRequest{
		TemplateName: "python3.12",
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
	})
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

	exec := New(manager, pods, nil, 1024)
	exec.Exec = func(ctx context.Context, _ *rest.Config, _, _ string, _ []string, _ io.Reader, _ io.Writer, _ io.Writer) error {
		<-ctx.Done()
		return ctx.Err()
	}

	result, _, err := exec.Execute(context.Background(), entry.SandboxID, `print("slow")`, 1)
	if err != nil {
		t.Fatalf("execute step: %v", err)
	}
	if !result.TimedOut || result.ExitCode != 124 {
		t.Fatalf("unexpected timeout result: %#v", result)
	}
}
