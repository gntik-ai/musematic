package events

import (
	"testing"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
)

func TestFanoutRegistryPublishesToMultipleSubscribers(t *testing.T) {
	registry := NewFanoutRegistry()
	first, unsubscribeFirst := registry.Subscribe("exec-1")
	defer unsubscribeFirst()
	second, unsubscribeSecond := registry.Subscribe("exec-1")
	defer unsubscribeSecond()

	event := &runtimev1.RuntimeEvent{ExecutionId: "exec-1"}
	registry.Publish(event)

	if got := <-first; got.ExecutionId != "exec-1" {
		t.Fatalf("unexpected first event: %+v", got)
	}
	if got := <-second; got.ExecutionId != "exec-1" {
		t.Fatalf("unexpected second event: %+v", got)
	}

	registry.Publish(nil)
	registry.Publish(&runtimev1.RuntimeEvent{ExecutionId: "no-subscribers"})
}
