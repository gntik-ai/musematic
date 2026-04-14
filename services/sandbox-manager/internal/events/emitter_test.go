package events

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	sandboxv1 "github.com/andrea-mucci/musematic/services/sandbox-manager/api/grpc/v1"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type producerStub struct {
	err         error
	delivery    kafka.Event
	message     *kafka.Message
	closeCalled bool
}

func (p *producerStub) Produce(message *kafka.Message, delivery chan kafka.Event) error {
	p.message = message
	if p.err != nil {
		return p.err
	}
	if p.delivery != nil {
		delivery <- p.delivery
	}
	return nil
}

func (p *producerStub) Close() {
	p.closeCalled = true
}

func TestEventEmitterEmit(t *testing.T) {
	t.Parallel()

	producer := &producerStub{
		delivery: &kafka.Message{TopicPartition: kafka.TopicPartition{}},
	}
	emitter := NewEventEmitter(producer)
	err := emitter.Emit(context.Background(), &sandboxv1.SandboxEvent{
		SandboxId: "sandbox-1",
	}, BuildEnvelope("sandbox.created", "sandbox-1", "exec-1", nil, map[string]string{"state": "creating"}))
	if err != nil {
		t.Fatalf("Emit() error = %v", err)
	}
	if producer.message == nil || string(producer.message.Key) != "sandbox-1" {
		t.Fatalf("unexpected message %+v", producer.message)
	}

	var payload map[string]json.RawMessage
	if err := json.Unmarshal(producer.message.Value, &payload); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	if _, ok := payload["event"]; !ok {
		t.Fatalf("expected event payload, got %s", string(producer.message.Value))
	}
}

func TestEventEmitterEmitReturnsContextAndDeliveryErrors(t *testing.T) {
	t.Parallel()

	cancelledCtx, cancel := context.WithCancel(context.Background())
	cancel()
	emitter := NewEventEmitter(&producerStub{})
	if err := emitter.Emit(cancelledCtx, &sandboxv1.SandboxEvent{SandboxId: "sandbox-1"}, Envelope{}); !errors.Is(err, context.Canceled) {
		t.Fatalf("Emit() error = %v", err)
	}

	deliveryErr := errors.New("delivery failed")
	emitter = NewEventEmitter(&producerStub{
		delivery: &kafka.Message{TopicPartition: kafka.TopicPartition{Error: deliveryErr}},
	})
	if err := emitter.Emit(context.Background(), &sandboxv1.SandboxEvent{SandboxId: "sandbox-1"}, Envelope{}); !errors.Is(err, deliveryErr) {
		t.Fatalf("Emit() error = %v", err)
	}
}

func TestEventEmitterHelpers(t *testing.T) {
	t.Parallel()

	if got := joinBrokers([]string{"one:9092", "two:9092"}); got != "one:9092,two:9092" {
		t.Fatalf("joinBrokers() = %q", got)
	}
	if got := joinBrokers(nil); got != "localhost:9092" {
		t.Fatalf("joinBrokers(nil) = %q", got)
	}
	if got := *stringPtr("sandbox.events"); got != "sandbox.events" {
		t.Fatalf("stringPtr() = %q", got)
	}

	producer, err := NewKafkaProducer([]string{"127.0.0.1:9092"})
	if err != nil {
		t.Fatalf("NewKafkaProducer() error = %v", err)
	}
	NewEventEmitter(producer).Close()

	stub := &producerStub{}
	NewEventEmitter(stub).Close()
	if !stub.closeCalled {
		t.Fatal("expected Close() to propagate to producer")
	}
}

func TestEventEmitterNoopAndProduceError(t *testing.T) {
	t.Parallel()

	if err := (*EventEmitter)(nil).Emit(context.Background(), &sandboxv1.SandboxEvent{SandboxId: "sandbox-1"}, Envelope{}); err != nil {
		t.Fatalf("nil EventEmitter.Emit() error = %v", err)
	}
	if err := (&EventEmitter{}).Emit(context.Background(), &sandboxv1.SandboxEvent{SandboxId: "sandbox-1"}, Envelope{}); err != nil {
		t.Fatalf("noop EventEmitter.Emit() error = %v", err)
	}
	(&EventEmitter{}).Close()

	expectedErr := errors.New("produce boom")
	emitter := NewEventEmitter(&producerStub{err: expectedErr})
	if err := emitter.Emit(context.Background(), &sandboxv1.SandboxEvent{SandboxId: "sandbox-1"}, Envelope{}); !errors.Is(err, expectedErr) {
		t.Fatalf("Emit() error = %v, want %v", err, expectedErr)
	}
}
