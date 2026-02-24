package main

import "github.com/confluentinc/confluent-kafka-go/v2/kafka"

type Producer struct {
	KafkaProducer *kafka.Producer
}

func NewProducer(kafkaServerAddr string) (*Producer, error) {

	config := &kafka.ConfigMap{
		"bootstrap.servers": kafkaServerAddr,
		"security.protocol": "PLAINTEXT",
	}

	kafkaProducer, err := kafka.NewProducer(config)
	if err != nil {
		return nil, err
	}

	return &Producer{
		KafkaProducer: kafkaProducer,
	}, nil
}
