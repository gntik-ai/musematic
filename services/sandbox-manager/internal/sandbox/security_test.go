package sandbox

import (
	"testing"

	v1 "k8s.io/api/core/v1"
)

func TestBuildPodSecurityContext(t *testing.T) {
	ctx := BuildPodSecurityContext()
	if ctx == nil || ctx.RunAsNonRoot == nil || !*ctx.RunAsNonRoot {
		t.Fatal("expected runAsNonRoot")
	}
	if ctx.RunAsUser == nil || *ctx.RunAsUser != 65534 {
		t.Fatalf("unexpected runAsUser: %v", ctx.RunAsUser)
	}
	if ctx.SeccompProfile == nil || ctx.SeccompProfile.Type != v1.SeccompProfileTypeRuntimeDefault {
		t.Fatal("expected RuntimeDefault seccomp profile")
	}
}

func TestBuildContainerSecurityContext(t *testing.T) {
	ctx := BuildContainerSecurityContext()
	if ctx == nil || ctx.AllowPrivilegeEscalation == nil || *ctx.AllowPrivilegeEscalation {
		t.Fatal("expected privilege escalation disabled")
	}
	if ctx.ReadOnlyRootFilesystem == nil || !*ctx.ReadOnlyRootFilesystem {
		t.Fatal("expected read-only root filesystem")
	}
	if len(ctx.Capabilities.Drop) != 1 || ctx.Capabilities.Drop[0] != "ALL" {
		t.Fatalf("unexpected capabilities: %#v", ctx.Capabilities)
	}
}
