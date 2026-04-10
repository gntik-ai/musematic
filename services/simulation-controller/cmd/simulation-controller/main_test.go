package main

import (
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
