package events

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type capturingProducer struct {
	last *kafka.Message
}

func (p *capturingProducer) Produce(msg *kafka.Message, deliveryChan chan kafka.Event) error {
	p.last = msg
	deliveryChan <- &kafka.Message{TopicPartition: kafka.TopicPartition{}}
	return nil
}

func (p *capturingProducer) Flush(int) int { return 0 }
func (p *capturingProducer) Close()        {}

func TestProduceReasoningEventHelpers(t *testing.T) {
	tests := []struct {
		name      string
		produceFn func(*KafkaProducer) error
		wantType  string
	}{
		{
			name: "debate round completed",
			produceFn: func(p *KafkaProducer) error {
				return p.ProduceDebateRoundCompleted(context.Background(), "exec-1", map[string]any{"round_number": 2})
			},
			wantType: EventDebateRoundCompleted,
		},
		{
			name: "react cycle completed",
			produceFn: func(p *KafkaProducer) error {
				return p.ProduceReactCycleCompleted(context.Background(), "exec-1", map[string]any{"cycle_number": 3})
			},
			wantType: EventReactCycleCompleted,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			fake := &capturingProducer{}
			producer := &KafkaProducer{producer: fake}
			if err := tc.produceFn(producer); err != nil {
				t.Fatalf("produce helper error = %v", err)
			}
			if fake.last == nil || fake.last.TopicPartition.Topic == nil || *fake.last.TopicPartition.Topic != "runtime.reasoning" {
				t.Fatalf("unexpected topic partition: %+v", fake.last)
			}
			if string(fake.last.Key) != "exec-1" {
				t.Fatalf("key = %q, want exec-1", string(fake.last.Key))
			}
			var body map[string]any
			if err := json.Unmarshal(fake.last.Value, &body); err != nil {
				t.Fatalf("json.Unmarshal() error = %v", err)
			}
			if body["event_type"] != tc.wantType || body["execution_id"] != "exec-1" || body["source"] != "reasoning-engine" {
				t.Fatalf("event body = %+v", body)
			}
			payload, ok := body["payload"].(map[string]any)
			if !ok || len(payload) != 1 {
				t.Fatalf("payload = %+v", body["payload"])
			}
		})
	}
}
