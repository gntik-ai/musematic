package metrics

import (
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestRegistryHandlerExportsRuntimeControllerMetrics(t *testing.T) {
	registry := NewRegistry()
	registry.IncLaunches()
	registry.ObserveLaunchDuration(1500 * time.Millisecond)
	registry.SetActiveRuntimes(3)
	registry.ObserveReconciliationDuration(250 * time.Millisecond)
	registry.IncHeartbeatTimeouts()

	recorder := httptest.NewRecorder()
	registry.Handler()(recorder, httptest.NewRequest("GET", "/metrics", nil))
	body := recorder.Body.String()

	for _, name := range []string{
		"runtime_controller_launches_total 1",
		"runtime_controller_launch_duration_seconds 1.5",
		"runtime_controller_active_runtimes 3",
		"runtime_controller_reconciliation_cycle_duration_seconds 0.25",
		"runtime_controller_heartbeat_timeouts_total 1",
	} {
		if !strings.Contains(body, name) {
			t.Fatalf("expected metric %q in body:\n%s", name, body)
		}
	}
}
