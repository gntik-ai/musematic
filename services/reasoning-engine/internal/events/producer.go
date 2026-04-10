package events

import (
	"context"
	"errors"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
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

func (p *KafkaProducer) Close() {
	if p == nil || p.producer == nil {
		return
	}
	p.producer.Flush(5000)
	p.producer.Close()
}
