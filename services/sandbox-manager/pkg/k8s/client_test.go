package k8s

import (
	"os"
	"path/filepath"
	"testing"
)

func TestNewClientFallsBackToKubeconfig(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("KUBERNETES_SERVICE_HOST", "")
	t.Setenv("KUBERNETES_SERVICE_PORT", "")

	kubeDir := filepath.Join(home, ".kube")
	if err := os.MkdirAll(kubeDir, 0o755); err != nil {
		t.Fatalf("MkdirAll() error = %v", err)
	}
	const kubeconfig = `apiVersion: v1
kind: Config
clusters:
- name: test
  cluster:
    server: https://example.invalid
contexts:
- name: test
  context:
    cluster: test
    user: test
current-context: test
users:
- name: test
  user:
    token: token
`
	if err := os.WriteFile(filepath.Join(kubeDir, "config"), []byte(kubeconfig), 0o600); err != nil {
		t.Fatalf("WriteFile() error = %v", err)
	}

	clientset, cfg, err := NewClient()
	if err != nil {
		t.Fatalf("NewClient() error = %v", err)
	}
	if clientset == nil || cfg == nil {
		t.Fatalf("expected client and config, got %v %v", clientset, cfg)
	}
	if cfg.Host != "https://example.invalid" {
		t.Fatalf("unexpected host %q", cfg.Host)
	}
}
