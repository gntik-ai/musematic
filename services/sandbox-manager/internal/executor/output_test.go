package executor

import (
	"context"
	"errors"
	"testing"

	v1 "k8s.io/api/core/v1"
)

type fakePodGetter struct {
	pod *v1.Pod
	err error
}

func (f fakePodGetter) GetPod(context.Context, string) (*v1.Pod, error) {
	if f.err != nil {
		return nil, f.err
	}
	return f.pod, nil
}

type fakeExitError struct{}

func (fakeExitError) Error() string   { return "exit" }
func (fakeExitError) ExitStatus() int { return 137 }

func TestParseStructuredOutput(t *testing.T) {
	if _, ok := ParseStructuredOutput("not-json"); ok {
		t.Fatal("expected invalid JSON to be rejected")
	}
	payload, ok := ParseStructuredOutput(`{"result":"42"}`)
	if !ok || payload == "" {
		t.Fatal("expected valid JSON to parse")
	}
}

func TestDetectOOM(t *testing.T) {
	if !DetectOOM(context.Background(), nil, "pod-1", fakeExitError{}) {
		t.Fatal("expected exit code 137 to be treated as OOM")
	}
	pod := &v1.Pod{
		Status: v1.PodStatus{
			ContainerStatuses: []v1.ContainerStatus{{
				LastTerminationState: v1.ContainerState{
					Terminated: &v1.ContainerStateTerminated{Reason: "OOMKilled"},
				},
			}},
		},
	}
	if !DetectOOM(context.Background(), fakePodGetter{pod: pod}, "pod-1", errors.New("boom")) {
		t.Fatal("expected pod status OOMKilled to be detected")
	}
}

func TestTruncateOutput(t *testing.T) {
	stdout, stderr, truncated := TruncateOutput("123456", "abcdef", 4)
	if stdout != "1234" || stderr != "abcd" || !truncated {
		t.Fatalf("unexpected truncate result: %q %q %v", stdout, stderr, truncated)
	}
}

type fakeExitCodeError struct {
	code int
}

func (e fakeExitCodeError) Error() string   { return "exit" }
func (e fakeExitCodeError) ExitStatus() int { return e.code }

func TestDetectOOMAndExitCodeHelpers(t *testing.T) {
	if DetectOOM(context.Background(), fakePodGetter{err: errors.New("lookup boom")}, "pod-1", errors.New("boom")) {
		t.Fatal("expected DetectOOM() to ignore lookup failures without OOM signal")
	}
	if got := exitCodeFor(nil, true, false); got != 124 {
		t.Fatalf("exitCodeFor(timeout) = %d", got)
	}
	if got := exitCodeFor(nil, false, true); got != 137 {
		t.Fatalf("exitCodeFor(oom) = %d", got)
	}
	if got := exitCodeFor(fakeExitCodeError{code: 23}, false, false); got != 23 {
		t.Fatalf("exitCodeFor(exit coder) = %d", got)
	}
	if got := exitCodeFor(errors.New("boom"), false, false); got != 1 {
		t.Fatalf("exitCodeFor(default) = %d", got)
	}
}
