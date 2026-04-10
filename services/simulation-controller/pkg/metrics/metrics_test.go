package metrics

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestMetricsRecordersDoNotPanic(t *testing.T) {
	t.Parallel()

	m := New()
	require.NotNil(t, m)
	require.NotPanics(t, func() {
		m.RecordSimulationCreated(context.Background())
		m.RecordSimulationTermination(context.Background(), "user_requested")
		m.RecordSimulationDuration(context.Background(), 12.5)
		m.RecordSimulationStatus(context.Background(), "RUNNING", 1)
		m.RecordArtifactsCollected(context.Background(), 2)
		m.RecordArtifactsBytes(context.Background(), 1024)
		m.RecordATESession(context.Background())
		m.RecordATEScenario(context.Background(), "passed")
	})
}
