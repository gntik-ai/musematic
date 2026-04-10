package persistence

import (
	"context"
	"sync"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type kafkaProducerClient interface {
	Produce(msg *kafka.Message, deliveryChan chan kafka.Event) error
	Events() chan kafka.Event
	Flush(timeoutMs int) int
	Close()
}

type KafkaProducer struct {
	producer  kafkaProducerClient
	closeOnce sync.Once
}

func NewKafkaProducer(brokers string) *KafkaProducer {
	if brokers == "" {
		return nil
	}

	producer, err := kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers":  brokers,
		"acks":               "all",
		"enable.idempotence": true,
	})
	if err != nil {
		panic(err)
	}

	p := &KafkaProducer{producer: producer}
	go func() {
		for range p.producer.Events() {
		}
	}()
	return p
}

func (p *KafkaProducer) Produce(ctx context.Context, topic, key string, value []byte) error {
	if p == nil || p.producer == nil {
		return nil
	}

	delivery := make(chan kafka.Event, 1)
	defer close(delivery)

	err := p.producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{Topic: &topic, Partition: kafka.PartitionAny},
		Key:            []byte(key),
		Value:          value,
	}, delivery)
	if err != nil {
		return err
	}

	select {
	case <-ctx.Done():
		return ctx.Err()
	case event := <-delivery:
		msg, ok := event.(*kafka.Message)
		if !ok {
			return nil
		}
		return msg.TopicPartition.Error
	}
}

func (p *KafkaProducer) Close() {
	if p == nil || p.producer == nil {
		return
	}
	p.closeOnce.Do(func() {
		p.producer.Flush(5000)
		p.producer.Close()
	})
}
