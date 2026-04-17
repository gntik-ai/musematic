package events

import (
	"context"
	"encoding/json"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

const (
	RuntimeLifecycleTopic = "runtime.lifecycle"
	MonitorAlertsTopic    = "monitor.alerts"
)

type Producer interface {
	Produce(*kafka.Message, chan kafka.Event) error
	Flush(int) int
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

func (e *EventEmitter) EmitLifecycle(ctx context.Context, event *runtimev1.RuntimeEvent, envelope Envelope) error {
	return e.emit(ctx, RuntimeLifecycleTopic, event, envelope, true)
}

func (e *EventEmitter) EmitDrift(ctx context.Context, event *runtimev1.RuntimeEvent, envelope Envelope) error {
	return e.emit(ctx, MonitorAlertsTopic, event, envelope, false)
}

func (e *EventEmitter) Close() {
	if e == nil || e.producer == nil {
		return
	}
	e.producer.Close()
}

func (e *EventEmitter) emit(_ context.Context, topic string, event *runtimev1.RuntimeEvent, envelope Envelope, wait bool) error {
	if e == nil || e.producer == nil {
		return nil
	}
	body, err := json.Marshal(map[string]any{"event": event, "envelope": envelope})
	if err != nil {
		return err
	}
	deliveryChan := make(chan kafka.Event, 1)
	if err := e.producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
		Value:          body,
	}, deliveryChan); err != nil {
		close(deliveryChan)
		return err
	}
	if wait {
		defer close(deliveryChan)
		if evt, ok := <-deliveryChan; ok {
			msg, ok := evt.(*kafka.Message)
			if ok && msg.TopicPartition.Error != nil {
				return msg.TopicPartition.Error
			}
		}
	}
	return nil
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
