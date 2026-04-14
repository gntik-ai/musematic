package logs

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
)

type logClientStub struct {
	reader io.ReadCloser
	err    error
}

func (s logClientStub) GetPodLogs(context.Context, string, bool) (io.ReadCloser, error) {
	if s.err != nil {
		return nil, s.err
	}
	return s.reader, nil
}

func TestStreamerPublishesLogLinesAndBuffersHistory(t *testing.T) {
	t.Parallel()

	fanout := NewFanoutRegistry(4)
	ch, cancel := fanout.Subscribe("sandbox-1")
	defer cancel()

	streamer := &Streamer{
		Client: logClientStub{reader: io.NopCloser(strings.NewReader("one\ntwo\n"))},
		Fanout: fanout,
	}
	if err := streamer.StreamPodLogs(context.Background(), "sandbox-1", "pod-1"); err != nil {
		t.Fatalf("StreamPodLogs() error = %v", err)
	}

	first := <-ch
	second := <-ch
	if first.Line != "one" || second.Line != "two" {
		t.Fatalf("unexpected streamed lines: %q %q", first.Line, second.Line)
	}
	if len(fanout.Buffered("sandbox-1")) != 2 {
		t.Fatal("expected buffered log history")
	}
}

func TestFanoutRegistrySlowSubscriberAndClose(t *testing.T) {
	t.Parallel()

	registry := NewFanoutRegistry(1)
	slow, _ := registry.Subscribe("sandbox-1")
	fast, _ := registry.Subscribe("sandbox-1")

	registry.Publish("sandbox-1", &sandboxv1.SandboxLogLine{Line: "first"})
	registry.Publish("sandbox-1", &sandboxv1.SandboxLogLine{Line: "second"})

	select {
	case <-fast:
	case <-time.After(time.Second):
		t.Fatal("expected fast subscriber to receive a line")
	}
	registry.Close("sandbox-1")
	_, _ = <-slow
	_, ok := <-slow
	if ok {
		t.Fatal("expected close to terminate subscriber channel")
	}
}

func TestStreamerPropagatesClientError(t *testing.T) {
	t.Parallel()

	expectedErr := errors.New("logs boom")
	streamer := &Streamer{
		Client: logClientStub{err: expectedErr},
		Fanout: NewFanoutRegistry(4),
	}
	if err := streamer.StreamPodLogs(context.Background(), "sandbox-1", "pod-1"); !errors.Is(err, expectedErr) {
		t.Fatalf("StreamPodLogs() error = %v, want %v", err, expectedErr)
	}
}
