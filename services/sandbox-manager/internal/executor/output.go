package executor

import (
	"context"
	"encoding/json"
	"errors"
	"strings"

	v1 "k8s.io/api/core/v1"
)

type PodGetter interface {
	GetPod(context.Context, string) (*v1.Pod, error)
}

func TruncateOutput(stdout string, stderr string, maxBytes int) (string, string, bool) {
	truncated := false
	if maxBytes > 0 && len(stdout) > maxBytes {
		stdout = stdout[:maxBytes]
		truncated = true
	}
	if maxBytes > 0 && len(stderr) > maxBytes {
		stderr = stderr[:maxBytes]
		truncated = true
	}
	return stdout, stderr, truncated
}

func DetectOOM(ctx context.Context, pods PodGetter, podName string, execErr error) bool {
	type exitCoder interface {
		ExitStatus() int
	}
	var codeErr exitCoder
	if errors.As(execErr, &codeErr) && codeErr.ExitStatus() == 137 {
		return true
	}
	if pods == nil {
		return false
	}
	pod, err := pods.GetPod(ctx, podName)
	if err != nil {
		return false
	}
	for _, status := range pod.Status.ContainerStatuses {
		if status.LastTerminationState.Terminated != nil && status.LastTerminationState.Terminated.Reason == "OOMKilled" {
			return true
		}
	}
	return false
}

func ParseStructuredOutput(stdout string) (string, bool) {
	trimmed := strings.TrimSpace(stdout)
	if trimmed == "" {
		return "", false
	}
	var payload map[string]any
	if err := json.Unmarshal([]byte(trimmed), &payload); err != nil {
		return "", false
	}
	return trimmed, true
}
