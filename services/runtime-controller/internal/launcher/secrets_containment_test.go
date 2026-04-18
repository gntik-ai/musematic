package launcher

import (
	"context"
	"testing"

	v1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes/fake"
)

func TestResolveSecretsUsesProjectedPathsWithoutLeakingValues(t *testing.T) {
	client := fake.NewSimpleClientset(&v1.Secret{
		ObjectMeta: metav1.ObjectMeta{Name: "db-creds", Namespace: "platform-execution"},
		Data: map[string][]byte{
			"DATABASE_URL": []byte("postgres://user:secret@db/prod"),
		},
	})

	projections, envs, err := ResolveSecrets(context.Background(), client, "platform-execution", []string{"db-creds"})
	if err != nil {
		t.Fatalf("ResolveSecrets returned error: %v", err)
	}
	if len(projections) != 1 || len(projections[0].Secret.Items) != 1 {
		t.Fatalf("unexpected projections: %+v", projections)
	}
	if projections[0].Secret.Items[0].Path != "DATABASE_URL" {
		t.Fatalf("unexpected secret projection path: %+v", projections[0].Secret.Items)
	}
	if len(envs) != 1 {
		t.Fatalf("unexpected env vars: %+v", envs)
	}
	if envs[0].Name != "SECRETS_REF_DATABASE_URL" {
		t.Fatalf("unexpected env name: %+v", envs[0])
	}
	if envs[0].Value != "/run/secrets/DATABASE_URL" {
		t.Fatalf("unexpected env value: %s", envs[0].Value)
	}
	if envs[0].Value == "postgres://user:secret@db/prod" {
		t.Fatalf("secret value leaked into env var")
	}
}
