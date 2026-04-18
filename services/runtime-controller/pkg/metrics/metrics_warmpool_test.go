package metrics

import (
	"net/http/httptest"
	"strings"
	"testing"
)

func TestWarmPoolMetricsSnapshot(t *testing.T) {
	registry := NewRegistry()
	registry.SetWarmPoolAvailable("ws-1", "python-3.12", 3)
	registry.SetWarmPoolTarget("ws-1", "python-3.12", 5)
	registry.SetWarmPoolWarming("ws-1", "python-3.12", 1)
	registry.IncWarmPoolDispatches("ws-1", "python-3.12")
	registry.IncColdStart("ws-1", "python-3.12")
	registry.IncColdStart("ws-1", "python-3.12")
	registry.ObserveWarmDispatchLatency("ws-1", "python-3.12", 450)

	snapshot := registry.Snapshot()
	if snapshot.WarmPoolAvailable["ws-1/python-3.12"] != 3 {
		t.Fatalf("unexpected available gauge: %+v", snapshot.WarmPoolAvailable)
	}
	if snapshot.WarmPoolTarget["ws-1/python-3.12"] != 5 {
		t.Fatalf("unexpected target gauge: %+v", snapshot.WarmPoolTarget)
	}
	if snapshot.WarmPoolWarming["ws-1/python-3.12"] != 1 {
		t.Fatalf("unexpected warming gauge: %+v", snapshot.WarmPoolWarming)
	}
	if snapshot.WarmPoolDispatches["ws-1/python-3.12"] != 1 {
		t.Fatalf("unexpected dispatch counter: %+v", snapshot.WarmPoolDispatches)
	}
	if snapshot.ColdStartCount["ws-1/python-3.12"] != 2 {
		t.Fatalf("unexpected cold start counter: %+v", snapshot.ColdStartCount)
	}
	latency := snapshot.WarmDispatchLatency["ws-1/python-3.12"]
	if latency.Count != 1 || latency.Sum != 450 {
		t.Fatalf("unexpected latency histogram snapshot: %+v", latency)
	}
}

func TestWarmPoolMetricsMethodsDoNotPanic(t *testing.T) {
	registry := NewRegistry()
	registry.SetWarmPoolAvailable("ws-1", "agent-a", 0)
	registry.SetWarmPoolTarget("ws-1", "agent-a", 0)
	registry.SetWarmPoolWarming("ws-1", "agent-a", 0)
	registry.IncWarmPoolDispatches("ws-1", "agent-a")
	registry.IncColdStart("ws-1", "agent-a")
	registry.ObserveWarmDispatchLatency("ws-1", "agent-a", 250)
}

func TestWarmPoolMetricsHandlerExportsLabeledSeries(t *testing.T) {
	registry := NewRegistry()
	registry.SetWarmPoolAvailable("ws-1", "python", 2)
	registry.SetWarmPoolTarget("ws-1", "python", 4)
	registry.SetWarmPoolWarming("ws-1", "python", 1)
	registry.IncWarmPoolDispatches("ws-1", "python")
	registry.IncColdStart("ws-1", "python")
	registry.ObserveWarmDispatchLatency("ws-1", "python", 450)

	recorder := httptest.NewRecorder()
	registry.Handler()(recorder, httptest.NewRequest("GET", "/metrics", nil))
	body := recorder.Body.String()

	for _, fragment := range []string{
		`runtime_controller_warm_pool_available{workspace_id="ws-1",agent_type="python"} 2`,
		`runtime_controller_warm_pool_target{workspace_id="ws-1",agent_type="python"} 4`,
		`runtime_controller_warm_pool_warming{workspace_id="ws-1",agent_type="python"} 1`,
		`runtime_controller_warm_pool_dispatches_total{workspace_id="ws-1",agent_type="python"} 1`,
		`runtime_controller_cold_start_count_total{workspace_id="ws-1",agent_type="python"} 1`,
		`runtime_controller_warm_dispatch_latency_ms_sum{workspace_id="ws-1",agent_type="python"} 450`,
		`runtime_controller_warm_dispatch_latency_ms_count{workspace_id="ws-1",agent_type="python"} 1`,
	} {
		if !strings.Contains(body, fragment) {
			t.Fatalf("expected metric fragment %q in body:\n%s", fragment, body)
		}
	}
}
