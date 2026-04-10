package launcher

import (
	"context"
	"testing"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func TestResolveSecretsBuildsProjectedVolumesAndEnvPointers(t *testing.T) {
	client := fake.NewSimpleClientset(&v1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: "api-secret", Namespace: "platform-execution"},
		Data: map[string][]byte{
			"api-key": []byte("super-secret"),
			"token":   []byte("secondary"),
		},
	})
	volumes, envs, err := ResolveSecrets(context.Background(), client, "platform-execution", []string{"api-secret"})
	if err != nil {
		t.Fatalf("ResolveSecrets returned error: %v", err)
	}
	if len(volumes) != 1 {
		t.Fatalf("expected 1 projection, got %d", len(volumes))
	}
	if len(envs) != 2 {
		t.Fatalf("expected 2 env vars, got %d", len(envs))
	}
	if envs[0].Value == "super-secret" {
		t.Fatalf("expected path pointer, got secret value")
	}
}

func TestResolveSecretsHandlesEmptyAndMissingSecrets(t *testing.T) {
	client := fake.NewSimpleClientset()

	volumes, envs, err := ResolveSecrets(context.Background(), client, "platform-execution", nil)
	if err != nil || volumes != nil || envs != nil {
		t.Fatalf("expected empty secret resolution, got volumes=%+v envs=%+v err=%v", volumes, envs, err)
	}

	if _, _, err := ResolveSecrets(context.Background(), client, "platform-execution", []string{"missing"}); err == nil {
		t.Fatalf("expected missing secret error")
	}
}

func TestKubernetesSecretResolverResolveUsesResolveSecrets(t *testing.T) {
	client := fake.NewSimpleClientset(&v1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: "api-secret", Namespace: "platform-execution"},
		Data:       map[string][]byte{"token": []byte("value")},
	})

	volumes, envs, err := (KubernetesSecretResolver{Client: client, Namespace: "platform-execution"}).Resolve(context.Background(), []string{"api-secret"})
	if err != nil {
		t.Fatalf("Resolve returned error: %v", err)
	}
	if len(volumes) != 1 || len(envs) != 1 {
		t.Fatalf("unexpected resolver output: volumes=%d envs=%d", len(volumes), len(envs))
	}
}
