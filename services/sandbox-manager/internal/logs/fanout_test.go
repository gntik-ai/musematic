package logs

import (
	"testing"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
)

func TestFanoutRegistryPublishesToMultipleSubscribers(t *testing.T) {
	registry := NewFanoutRegistry(4)
	ch1, cancel1 := registry.Subscribe("sandbox-1")
	ch2, cancel2 := registry.Subscribe("sandbox-1")
	defer cancel1()
	defer cancel2()

	line := &sandboxv1.SandboxLogLine{Line: "hello"}
	registry.Publish("sandbox-1", line)

	if got := (<-ch1).Line; got != "hello" {
		t.Fatalf("unexpected line for subscriber 1: %s", got)
	}
	if got := (<-ch2).Line; got != "hello" {
		t.Fatalf("unexpected line for subscriber 2: %s", got)
	}
	if len(registry.Buffered("sandbox-1")) != 1 {
		t.Fatal("expected line in history buffer")
	}
}

func TestNewFanoutRegistryUsesDefaultBufferSize(t *testing.T) {
	registry := NewFanoutRegistry(0)
	ch, cancel := registry.Subscribe("sandbox-1")
	defer cancel()

	registry.Publish("sandbox-1", &sandboxv1.SandboxLogLine{Line: "hello"})
	if got := (<-ch).Line; got != "hello" {
		t.Fatalf("unexpected line %q", got)
	}
}
