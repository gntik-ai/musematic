package events

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	runtimev1 "github.com/andrea-mucci/musematic/services/runtime-controller/api/grpc/v1"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type fakeProducer struct {
	produced    []*kafka.Message
	produceErr  error
	deliveryErr error
	closed      bool
}

func (f *fakeProducer) Produce(msg *kafka.Message, delivery chan kafka.Event) error {
	if f.produceErr != nil {
		return f.produceErr
	}
	copied := *msg
	copied.Value = append([]byte(nil), msg.Value...)
	f.produced = append(f.produced, &copied)
	if delivery != nil {
		delivery <- &kafka.Message{TopicPartition: kafka.TopicPartition{Error: f.deliveryErr}}
	}
	return nil
}

func (f *fakeProducer) Flush(int) int { return 0 }

func (f *fakeProducer) Close() { f.closed = true }

func TestJoinBrokers(t *testing.T) {
	if got := joinBrokers(nil); got != "localhost:9092" {
		t.Fatalf("unexpected default broker list: %s", got)
	}
	if got := joinBrokers([]string{"k1:9092", "k2:9092"}); got != "k1:9092,k2:9092" {
		t.Fatalf("unexpected joined brokers: %s", got)
	}
}

func TestEmitLifecyclePublishesEnvelope(t *testing.T) {
	producer := &fakeProducer{}
	emitter := NewEventEmitter(producer)
	event := &runtimev1.RuntimeEvent{ExecutionId: "exec-1", EventType: runtimev1.RuntimeEventType_RUNTIME_EVENT_LAUNCHED}
	envelope := BuildEnvelope("runtime.launched", "rt-1", "exec-1", &runtimev1.CorrelationContext{TraceId: "trace-1"}, map[string]string{"state": "running"})

	if err := emitter.EmitLifecycle(context.Background(), event, envelope); err != nil {
		t.Fatalf("EmitLifecycle returned error: %v", err)
	}
	if len(producer.produced) != 1 {
		t.Fatalf("expected one produced message")
	}
	if topic := *producer.produced[0].TopicPartition.Topic; topic != RuntimeLifecycleTopic {
		t.Fatalf("unexpected topic: %s", topic)
	}

	var payload map[string]json.RawMessage
	if err := json.Unmarshal(producer.produced[0].Value, &payload); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if len(payload["event"]) == 0 || len(payload["envelope"]) == 0 {
		t.Fatalf("unexpected payload: %s", string(producer.produced[0].Value))
	}
}

func TestEmitLifecyclePropagatesDeliveryError(t *testing.T) {
	emitter := NewEventEmitter(&fakeProducer{deliveryErr: errors.New("delivery failed")})

	err := emitter.EmitLifecycle(context.Background(), &runtimev1.RuntimeEvent{}, BuildEnvelope("runtime.launched", "rt", "exec", nil, nil))
	if err == nil {
		t.Fatalf("expected delivery error")
	}
}

func TestEmitDriftIsNonBlocking(t *testing.T) {
	producer := &fakeProducer{}
	emitter := NewEventEmitter(producer)

	if err := emitter.EmitDrift(context.Background(), &runtimev1.RuntimeEvent{ExecutionId: "exec-1"}, BuildEnvelope("runtime.failed", "rt-1", "exec-1", nil, nil)); err != nil {
		t.Fatalf("EmitDrift returned error: %v", err)
	}
	if len(producer.produced) != 1 {
		t.Fatalf("expected one produced message")
	}
	if topic := *producer.produced[0].TopicPartition.Topic; topic != MonitorAlertsTopic {
		t.Fatalf("unexpected topic: %s", topic)
	}
}

func TestEventEmitterCloseHandlesNilProducer(t *testing.T) {
	var nilEmitter *EventEmitter
	nilEmitter.Close()

	producer := &fakeProducer{}
	NewEventEmitter(producer).Close()
	if !producer.closed {
		t.Fatalf("expected producer to be closed")
	}
}

func TestNewKafkaProducerReturnsProducerInstance(t *testing.T) {
	producer, err := NewKafkaProducer(nil)
	if err != nil {
		t.Fatalf("NewKafkaProducer returned error: %v", err)
	}
	producer.Close()
}
