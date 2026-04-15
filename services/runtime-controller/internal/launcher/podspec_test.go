package launcher

import (
	"testing"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	v1 "k8s.io/api/core/v1"
)

func TestBuildPodSpecAppliesLabelsVolumesAndResources(t *testing.T) {
	contract := &runtimev1.RuntimeContract{
		AgentRevision: "agent.test/v1",
		CorrelationContext: &runtimev1.CorrelationContext{
			ExecutionId: "exec-12345678-abcd",
			WorkspaceId: "ws-test",
		},
		ResourceLimits: &runtimev1.ResourceLimits{
			CpuRequest:    "250m",
			CpuLimit:      "500m",
			MemoryRequest: "256Mi",
			MemoryLimit:   "512Mi",
		},
		EnvVars: map[string]string{"FOO": "bar", "SANITIZER_PATTERNS_URL": "https://config/patterns.json"},
	}

	pod := BuildPodSpec(contract, "https://example.invalid/package.tgz", "platform-execution", []v1.VolumeProjection{}, nil)
	if pod.Name == "" || pod.Namespace != "platform-execution" {
		t.Fatalf("unexpected metadata: %+v", pod.ObjectMeta)
	}
	if pod.Labels["managed_by"] != "runtime-controller" {
		t.Fatalf("missing managed_by label: %+v", pod.Labels)
	}
	if len(pod.Spec.InitContainers) != 1 || len(pod.Spec.Containers) != 1 {
		t.Fatalf("unexpected container counts: %+v", pod.Spec)
	}
	if got := pod.Spec.Containers[0].Resources.Requests.Cpu().String(); got != "250m" {
		t.Fatalf("unexpected cpu request: %s", got)
	}
	if pod.Spec.Containers[0].Env[2].Value != "https://config/patterns.json" {
		t.Fatalf("unexpected sanitizer URL env: %+v", pod.Spec.Containers[0].Env)
	}
}

func TestPodSpecHelpersHandleSecretMountsAndEmptyValues(t *testing.T) {
	mounts := buildVolumeMounts([]v1.VolumeProjection{{}})
	if len(mounts) != 2 || mounts[1].MountPath != "/run/secrets" {
		t.Fatalf("unexpected mounts: %+v", mounts)
	}
	if sanitizeLabelValue("###") != "unknown" {
		t.Fatalf("expected unknown for invalid label")
	}
	if got := sanitizeLabelValue("Agent/FQN.With:Chars"); got != "agent-fqn.with-chars" {
		t.Fatalf("unexpected sanitized label: %s", got)
	}
	if got := sanitizeLabelValue("abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnop"); len(got) != 63 {
		t.Fatalf("expected truncated label, got %q len=%d", got, len(got))
	}
	if got := buildPodName(""); got != "runtime-unknown" {
		t.Fatalf("unexpected pod name: %s", got)
	}
	if correlationContext(nil).ExecutionId != "" || correlationContext(&runtimev1.RuntimeContract{}).WorkspaceId != "" {
		t.Fatalf("expected empty fallback correlation context")
	}
}
