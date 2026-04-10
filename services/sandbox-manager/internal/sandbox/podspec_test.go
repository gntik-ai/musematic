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
