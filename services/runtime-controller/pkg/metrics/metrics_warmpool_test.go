package metrics

import (
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
