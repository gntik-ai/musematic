package escalation

import (
	"context"
	"errors"
	"testing"
)

type producerStub struct {
	topics []string
	err    error
}

func (p *producerStub) Produce(_ context.Context, topic, _ string, _ []byte) error {
	if p.err != nil {
		return p.err
	}
	p.topics = append(p.topics, topic)
	return nil
}

func TestRouterEscalate(t *testing.T) {
	producer := &producerStub{}
	router := NewRouter(producer)
	if err := router.Escalate(context.Background(), "loop-1", "exec-1", 3, 0.5, 0.7); err != nil {
		t.Fatalf("Escalate() error = %v", err)
	}
	if len(producer.topics) != 1 || producer.topics[0] != "monitor.alerts" {
		t.Fatalf("topics = %+v", producer.topics)
	}

	if err := (*Router)(nil).Escalate(context.Background(), "loop-1", "exec-1", 3, 0.5, 0.7); err != nil {
		t.Fatalf("nil router Escalate() error = %v", err)
	}
	if err := NewRouter(nil).Escalate(context.Background(), "loop-1", "exec-1", 3, 0.5, 0.7); err != nil {
		t.Fatalf("nil producer Escalate() error = %v", err)
	}

	expected := errors.New("publish failed")
	if err := NewRouter(&producerStub{err: expected}).Escalate(context.Background(), "loop-1", "exec-1", 3, 0.5, 0.7); !errors.Is(err, expected) {
		t.Fatalf("Escalate() error = %v, want %v", err, expected)
	}
}
