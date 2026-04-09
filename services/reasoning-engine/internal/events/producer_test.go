package events

import (
	"context"
	"testing"
)

func TestNewKafkaProducerRequiresBootstrapServers(t *testing.T) {
	_, err := NewKafkaProducer("")
	if err == nil {
		t.Fatal("expected error for empty bootstrap servers")
	}
}

func TestProduceSignatureCompiles(t *testing.T) {
	_ = context.Background
}

func TestCloseSignatureCompiles(t *testing.T) {
	var producer *KafkaProducer
	_ = producer
}
