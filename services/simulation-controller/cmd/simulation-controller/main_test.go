package main

import (
	"math"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestLoadConfigUsesEnvOverrides(t *testing.T) {
	t.Setenv("GRPC_PORT", "50099")
	t.Setenv("SIMULATION_BUCKET", "custom-bucket")
	t.Setenv("SIMULATION_NAMESPACE", "custom-namespace")
	t.Setenv("ORPHAN_SCAN_INTERVAL_SECONDS", "10")
	t.Setenv("DEFAULT_MAX_DURATION_SECONDS", "90")

	cfg := loadConfig()
	require.Equal(t, 50099, cfg.grpcPort)
	require.Equal(t, "custom-bucket", cfg.simulationBucket)
	require.Equal(t, "custom-namespace", cfg.simulationNamespace)
	require.EqualValues(t, 90, cfg.defaultMaxDuration)
}

func TestHelperFunctionsCoverFallbackPaths(t *testing.T) {
	t.Setenv("STRING_KEY", "")
	t.Setenv("INT_KEY", "not-an-int")

	require.Equal(t, "fallback", envString("STRING_KEY", "fallback"))
	require.Equal(t, 12, envInt("INT_KEY", 12))
	require.EqualValues(t, math.MaxInt32, safeInt32(1<<62))
	require.EqualValues(t, math.MinInt32, safeInt32(-1<<62))
}

func TestNewKubernetesClientReturnsErrorForMissingConfig(t *testing.T) {
	t.Parallel()

	_, _, err := newKubernetesClient("/definitely/missing/kubeconfig")
	require.Error(t, err)
}

func TestNewKubernetesClientLoadsExplicitKubeconfig(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	kubeconfig := filepath.Join(dir, "config")
	require.NoError(t, os.WriteFile(kubeconfig, []byte(`
apiVersion: v1
kind: Config
clusters:
- name: local
  cluster:
    server: https://127.0.0.1:6443
contexts:
- name: local
  context:
    cluster: local
    user: local
current-context: local
users:
- name: local
  user:
    token: token
`), 0o600))

	clientset, cfg, err := newKubernetesClient(kubeconfig)
	require.NoError(t, err)
	require.NotNil(t, clientset)
	require.Equal(t, "https://127.0.0.1:6443", cfg.Host)
}
