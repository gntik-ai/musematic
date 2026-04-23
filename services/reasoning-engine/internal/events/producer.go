package events

import (
	"context"
	"encoding/json"
	"errors"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

const (
	EventDebateRoundCompleted = "reasoning.debate.round_completed"
	EventReactCycleCompleted  = "reasoning.react.cycle_completed"
)

type KafkaProducer struct {
	producer kafkaProducerClient
}

type kafkaProducerClient interface {
	Produce(msg *kafka.Message, deliveryChan chan kafka.Event) error
	Flush(timeoutMs int) int
	Close()
}

func NewKafkaProducer(bootstrapServers string) (*KafkaProducer, error) {
	if bootstrapServers == "" {
		return nil, errors.New("bootstrap servers are required")
	}

	producer, err := kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers":  bootstrapServers,
		"acks":               "all",
		"enable.idempotence": true,
	})
	if err != nil {
		return nil, err
	}

	return &KafkaProducer{producer: producer}, nil
}

func (p *KafkaProducer) Produce(ctx context.Context, topic string, key string, valueJSON []byte) error {
	if p == nil || p.producer == nil {
		return errors.New("producer is not initialized")
	}

	deliveryChan := make(chan kafka.Event, 1)
	defer close(deliveryChan)

	err := p.producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
		Key:            []byte(key),
		Value:          valueJSON,
	}, deliveryChan)
	if err != nil {
		return err
	}

	select {
	case <-ctx.Done():
		return ctx.Err()
	case event := <-deliveryChan:
		message, ok := event.(*kafka.Message)
		if !ok {
			return errors.New("unexpected delivery event type")
		}
		return message.TopicPartition.Error
	}
}

func (p *KafkaProducer) ProduceDebateRoundCompleted(
	ctx context.Context,
	executionID string,
	payload map[string]any,
) error {
	return p.produceReasoningEvent(ctx, EventDebateRoundCompleted, executionID, payload)
}

func (p *KafkaProducer) ProduceReactCycleCompleted(
	ctx context.Context,
	executionID string,
	payload map[string]any,
) error {
	return p.produceReasoningEvent(ctx, EventReactCycleCompleted, executionID, payload)
}

func (p *KafkaProducer) produceReasoningEvent(
	ctx context.Context,
	eventType string,
	executionID string,
	payload map[string]any,
) error {
	body, err := json.Marshal(map[string]any{
		"event_type":   eventType,
		"version":      "1.0",
		"source":       "reasoning-engine",
		"execution_id": executionID,
		"occurred_at":  time.Now().UTC().Format(time.RFC3339Nano),
		"payload":      payload,
	})
	if err != nil {
		return err
	}
	return p.Produce(ctx, "runtime.reasoning", executionID, body)
}

func (p *KafkaProducer) Close() {
	if p == nil || p.producer == nil {
		return
	}
	p.producer.Flush(5000)
	p.producer.Close()
}
