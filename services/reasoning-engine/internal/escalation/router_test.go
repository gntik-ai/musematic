package escalation

import (
	"context"
	"testing"
)

type producerStub struct {
	topics []string
}

func (p *producerStub) Produce(_ context.Context, topic, _ string, _ []byte) error {
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
}
