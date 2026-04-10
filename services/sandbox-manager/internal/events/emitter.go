package events

import (
	"context"
	"encoding/json"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

const SandboxEventsTopic = "sandbox.events"

type Producer interface {
	Produce(*kafka.Message, chan kafka.Event) error
	Close()
}

type EventEmitter struct {
	producer Producer
}

func NewEventEmitter(producer Producer) *EventEmitter {
	return &EventEmitter{producer: producer}
}

func NewKafkaProducer(brokers []string) (Producer, error) {
	return kafka.NewProducer(&kafka.ConfigMap{"bootstrap.servers": joinBrokers(brokers)})
}

func (e *EventEmitter) Close() {
	if e == nil || e.producer == nil {
		return
	}
	e.producer.Close()
}

func (e *EventEmitter) Emit(ctx context.Context, event *sandboxv1.SandboxEvent, envelope Envelope) error {
	if e == nil || e.producer == nil {
		return nil
	}
	body, err := json.Marshal(map[string]any{
		"event":    event,
		"envelope": envelope,
	})
	if err != nil {
		return err
	}
	delivery := make(chan kafka.Event, 1)
	defer close(delivery)
	if err := e.producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: stringPtr(SandboxEventsTopic), Partition: kafka.PartitionAny},
		Key:            []byte(event.SandboxId),
		Value:          body,
	}, delivery); err != nil {
		return err
	}
	select {
	case <-ctx.Done():
		return ctx.Err()
	case raw := <-delivery:
		msg, ok := raw.(*kafka.Message)
		if ok && msg.TopicPartition.Error != nil {
			return msg.TopicPartition.Error
		}
		return nil
	}
}

func joinBrokers(brokers []string) string {
	if len(brokers) == 0 {
		return "localhost:9092"
	}
	out := brokers[0]
	for _, broker := range brokers[1:] {
		out += "," + broker
	}
	return out
}

func stringPtr(value string) *string {
	return &value
}
