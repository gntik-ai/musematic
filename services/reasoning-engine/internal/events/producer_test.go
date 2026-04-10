package events

import (
	"context"
	"errors"
	"testing"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type fakeProducer struct {
	event   kafka.Event
	err     error
	flushed bool
	closed  bool
}

func (f *fakeProducer) Produce(_ *kafka.Message, deliveryChan chan kafka.Event) error {
	if f.err != nil {
		return f.err
	}
	deliveryChan <- f.event
	return nil
}

func (f *fakeProducer) Flush(int) int {
	f.flushed = true
	return 0
}

func (f *fakeProducer) Close() {
	f.closed = true
}

func TestNewKafkaProducerRequiresBootstrapServers(t *testing.T) {
	_, err := NewKafkaProducer("")
	if err == nil {
		t.Fatal("expected error for empty bootstrap servers")
	}
}

func TestProduceRequiresInitializedProducer(t *testing.T) {
	var producer *KafkaProducer
	if err := producer.Produce(context.Background(), "topic", "key", []byte("value")); err == nil {
		t.Fatal("expected initialization error")
	}
}

func TestProduceReturnsDeliveryError(t *testing.T) {
	fake := &fakeProducer{
		event: &kafka.Message{TopicPartition: kafka.TopicPartition{Error: errors.New("delivery failed")}},
	}
	producer := &KafkaProducer{producer: fake}

	err := producer.Produce(context.Background(), "topic", "key", []byte("value"))
	if err == nil || err.Error() != "delivery failed" {
		t.Fatalf("Produce() error = %v, want delivery failed", err)
	}
}

func TestProduceRejectsUnexpectedDeliveryEvent(t *testing.T) {
	fake := &fakeProducer{event: kafka.Error{}}
	producer := &KafkaProducer{producer: fake}

	err := producer.Produce(context.Background(), "topic", "key", []byte("value"))
	if err == nil || err.Error() != "unexpected delivery event type" {
		t.Fatalf("Produce() error = %v, want unexpected delivery event type", err)
	}
}

func TestProduceSucceeds(t *testing.T) {
	fake := &fakeProducer{
		event: &kafka.Message{TopicPartition: kafka.TopicPartition{}},
	}
	producer := &KafkaProducer{producer: fake}

	if err := producer.Produce(context.Background(), "topic", "key", []byte("value")); err != nil {
		t.Fatalf("Produce() error = %v", err)
	}
}

func TestCloseHandlesNilAndInitializedProducer(t *testing.T) {
	var nilProducer *KafkaProducer
	nilProducer.Close()

	fake := &fakeProducer{}
	producer := &KafkaProducer{producer: fake}
	producer.Close()

	if !fake.flushed || !fake.closed {
		t.Fatalf("expected flush and close to be invoked, got flushed=%v closed=%v", fake.flushed, fake.closed)
	}
}
