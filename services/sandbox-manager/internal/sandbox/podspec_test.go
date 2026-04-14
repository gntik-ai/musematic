package sandbox

import (
	"testing"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/andrea-mucci/musematic/services/sandbox-manager/internal/templates"
	v1 "k8s.io/api/core/v1"
)

func TestBuildPodSpecHardeningAndNetworkDisabled(t *testing.T) {
	pod, err := BuildPodSpec("sandbox-12345678", templates.PythonTemplate(), &sandboxv1.CreateSandboxRequest{
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
		NetworkEnabled: false,
	}, "platform-execution", 300*time.Second)
	if err != nil {
		t.Fatalf("build pod spec: %v", err)
	}
	if pod.Spec.DNSPolicy != v1.DNSNone {
		t.Fatalf("expected DNSNone, got %s", pod.Spec.DNSPolicy)
	}
	if pod.Spec.AutomountServiceAccountToken == nil || *pod.Spec.AutomountServiceAccountToken {
		t.Fatal("expected automountServiceAccountToken disabled")
	}
	if pod.Spec.EnableServiceLinks == nil || *pod.Spec.EnableServiceLinks {
		t.Fatal("expected enableServiceLinks disabled")
	}
	if pod.Labels["musematic/network-allowed"] != "" {
		t.Fatal("network-enabled label should not be present")
	}
	if len(pod.Spec.Volumes) != 3 {
		t.Fatalf("expected 3 volumes, got %d", len(pod.Spec.Volumes))
	}
}

func TestBuildPodSpecNetworkEnabled(t *testing.T) {
	pod, err := BuildPodSpec("sandbox-12345678", templates.NodeTemplate(), &sandboxv1.CreateSandboxRequest{
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
		NetworkEnabled: true,
	}, "platform-execution", 300*time.Second)
	if err != nil {
		t.Fatalf("build pod spec: %v", err)
	}
	if pod.Spec.DNSPolicy != v1.DNSClusterFirst {
		t.Fatalf("expected ClusterFirst, got %s", pod.Spec.DNSPolicy)
	}
	if pod.Labels["musematic/network-allowed"] != "true" {
		t.Fatal("expected network-enabled label")
	}
}

func TestPodspecHelpers(t *testing.T) {
	t.Parallel()

	base := &sandboxv1.ResourceLimits{
		CpuRequest:    "250m",
		CpuLimit:      "500m",
		MemoryRequest: "256Mi",
		MemoryLimit:   "512Mi",
	}
	merged := mergeResourceLimits(base, &sandboxv1.ResourceLimits{CpuLimit: "750m", MemoryLimit: "1Gi"})
	if merged.CpuRequest != "250m" || merged.CpuLimit != "750m" || merged.MemoryRequest != "256Mi" || merged.MemoryLimit != "1Gi" {
		t.Fatalf("unexpected merged limits %+v", merged)
	}

	copied := mergeResourceLimits(base, nil)
	if copied == base || copied.CpuRequest != base.CpuRequest {
		t.Fatalf("expected nil override to return a copy, got %+v", copied)
	}

	if shortID("1234567890") != "12345678" {
		t.Fatalf("shortID(long) = %q", shortID("1234567890"))
	}
	if shortID("short") != "short" {
		t.Fatalf("shortID(short) = %q", shortID("short"))
	}

	fromNil := mergeResourceLimits(nil, &sandboxv1.ResourceLimits{CpuRequest: "100m"})
	if fromNil.CpuRequest != "100m" {
		t.Fatalf("unexpected nil-base merge %+v", fromNil)
	}
}

func TestBuildPodSpecIncludesEnvVarsAndDeadline(t *testing.T) {
	t.Parallel()

	pod, err := BuildPodSpec("sandbox-1234567890", templates.PythonTemplate(), &sandboxv1.CreateSandboxRequest{
		Correlation: &sandboxv1.CorrelationContext{
			WorkspaceId: "ws-1",
			ExecutionId: "exec-1",
		},
		EnvVars: map[string]string{"ENV": "1"},
	}, "platform-execution", 90*time.Second)
	if err != nil {
		t.Fatalf("BuildPodSpec() error = %v", err)
	}
	if pod.Name != "sandbox-sandbox-" {
		t.Fatalf("unexpected pod name %q", pod.Name)
	}
	if pod.Spec.ActiveDeadlineSeconds == nil || *pod.Spec.ActiveDeadlineSeconds != 90 {
		t.Fatalf("unexpected active deadline %+v", pod.Spec.ActiveDeadlineSeconds)
	}
	if len(pod.Spec.Containers) != 1 || len(pod.Spec.Containers[0].Env) != 1 {
		t.Fatalf("expected env vars to be propagated, got %+v", pod.Spec.Containers)
	}
}
