package persistence

import (
	"sync"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type Producer interface {
	Produce(topic, key string, value []byte) error
	Close()
}

type kafkaProducerClient interface {
	Produce(msg *kafka.Message, deliveryChan chan kafka.Event) error
	Events() chan kafka.Event
	Flush(timeoutMs int) int
	Close()
}

type KafkaProducer struct {
	producer        kafkaProducerClient
	deliveryTimeout time.Duration
	closeOnce       sync.Once
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

	wrapped := &KafkaProducer{
		producer:        producer,
		deliveryTimeout: 5 * time.Second,
	}
	go func() {
		for range wrapped.producer.Events() {
		}
	}()
	return wrapped
}

func (p *KafkaProducer) Produce(topic, key string, value []byte) error {
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
	case event := <-delivery:
		msg, ok := event.(*kafka.Message)
		if !ok {
			return nil
		}
		return msg.TopicPartition.Error
	case <-time.After(p.deliveryTimeout):
		return nil
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
