package executor

import (
	"bytes"
	"context"
	"errors"
	"io"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/sandbox"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/templates"
	k8spkg "github.com/andrea-mucci/musematic/services/sandbox-manager/pkg/k8s"
	"google.golang.org/protobuf/types/known/durationpb"
	"k8s.io/client-go/rest"
)

type ExecFunc func(context.Context, *rest.Config, string, string, []string, io.Reader, io.Writer, io.Writer) error

type Executor struct {
	Manager       *sandbox.Manager
	Pods          PodGetter
	RestConfig    *rest.Config
	Exec          ExecFunc
	MaxOutputSize int
}

func New(manager *sandbox.Manager, pods PodGetter, cfg *rest.Config, maxOutputSize int) *Executor {
	return &Executor{
		Manager:       manager,
		Pods:          pods,
		RestConfig:    cfg,
		Exec:          k8spkg.ExecInPod,
		MaxOutputSize: maxOutputSize,
	}
}

func (e *Executor) Execute(ctx context.Context, sandboxID string, code string, timeoutOverride int32) (*sandboxv1.ExecutionResult, int32, error) {
	entry, err := e.Manager.Get(sandboxID)
	if err != nil {
		return nil, 0, sandbox.ErrSandboxNotFound
	}
	if entry.State != sandboxv1.SandboxState_SANDBOX_STATE_READY {
		return nil, 0, sandbox.ErrInvalidState
	}
	if err := e.Manager.Transition(ctx, sandboxID, sandboxv1.SandboxState_SANDBOX_STATE_READY, sandboxv1.SandboxState_SANDBOX_STATE_EXECUTING, ""); err != nil {
		return nil, 0, err
	}
	template, err := templates.Lookup(entry.Template)
	if err != nil {
		return nil, 0, err
	}
	timeout := timeoutOverride
	if timeout <= 0 {
		timeout = template.TimeoutSeconds
	}
	command := BuildCommand(template, code, timeout)

	start := time.Now()
	execCtx, cancel := context.WithTimeout(ctx, time.Duration(timeout+5)*time.Second)
	defer cancel()

	var stdoutBuf bytes.Buffer
	var stderrBuf bytes.Buffer
	err = e.Exec(execCtx, e.RestConfig, entry.PodNamespace, entry.PodName, command, nil, &stdoutBuf, &stderrBuf)

	stdout, stderr, truncated := TruncateOutput(stdoutBuf.String(), stderrBuf.String(), e.MaxOutputSize)
	timedOut := errors.Is(execCtx.Err(), context.DeadlineExceeded)
	oomKilled := DetectOOM(ctx, e.Pods, entry.PodName, err)
	exitCode := exitCodeFor(err, timedOut, oomKilled)
	if exitCode == 124 {
		timedOut = true
	}
	if structured, ok := ParseStructuredOutput(stdout); ok && entry.Template == "code-as-reasoning" {
		stdout = ""
		return e.finish(ctx, sandboxID, start, stdout, stderr, structured, truncated, timedOut, oomKilled, exitCode, err)
	}
	return e.finish(ctx, sandboxID, start, stdout, stderr, "", truncated, timedOut, oomKilled, exitCode, err)
}

func (e *Executor) finish(
	ctx context.Context,
	sandboxID string,
	start time.Time,
	stdout string,
	stderr string,
	structured string,
	truncated bool,
	timedOut bool,
	oomKilled bool,
	exitCode int32,
	execErr error,
) (*sandboxv1.ExecutionResult, int32, error) {
	duration := time.Since(start)
	stepNum, err := e.Manager.RecordStep(sandboxID, duration)
	if err != nil {
		return nil, 0, err
	}
	if timedOut || oomKilled {
		_ = e.Manager.MarkFailed(ctx, sandboxID, stderr)
	} else {
		_ = e.Manager.Transition(ctx, sandboxID, sandboxv1.SandboxState_SANDBOX_STATE_EXECUTING, sandboxv1.SandboxState_SANDBOX_STATE_READY, "")
	}
	if execErr != nil && !timedOut {
		type exitCoder interface{ ExitStatus() int }
		var codeErr exitCoder
		if !errors.As(execErr, &codeErr) && !oomKilled {
			return nil, 0, execErr
		}
	}
	return &sandboxv1.ExecutionResult{
		Stdout:           stdout,
		Stderr:           stderr,
		ExitCode:         exitCode,
		Duration:         durationpb.New(duration),
		TimedOut:         timedOut,
		OomKilled:        oomKilled,
		StructuredOutput: structured,
		OutputTruncated:  truncated,
	}, stepNum, nil
}

func exitCodeFor(execErr error, timedOut bool, oomKilled bool) int32 {
	if timedOut {
		return 124
	}
	if oomKilled {
		return 137
	}
	if execErr == nil {
		return 0
	}
	type exitCoder interface {
		ExitStatus() int
	}
	var codeErr exitCoder
	if errors.As(execErr, &codeErr) {
		return int32(codeErr.ExitStatus())
	}
	return 1
}
