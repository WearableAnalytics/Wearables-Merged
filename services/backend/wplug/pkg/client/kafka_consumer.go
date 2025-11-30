package client

import (
	"context"
	"log"
	"wplug/pkg/message"
	"wplug/pkg/waiter"

	jsoniter "github.com/json-iterator/go"
	kafka "github.com/segmentio/kafka-go"
	//franz "github.com/twmb/franz-go/pkg/kgo"
)

type KafkaConsumer struct {
	Reader         *kafka.Reader
	ResponseWaiter *waiter.ResponseWaiter
	Config         kafka.ReaderConfig
	jsonFast       jsoniter.API
}

func NewKafkaConsumer(rw *waiter.ResponseWaiter, topic string, partition int, maxBytes int, brokers ...string) *KafkaConsumer {
	config := kafka.ReaderConfig{
		Brokers:   brokers,
		Topic:     topic,
		Partition: partition,
		MaxBytes:  maxBytes,
	}

	return &KafkaConsumer{
		Config:         config,
		ResponseWaiter: rw,
		jsonFast:       jsoniter.ConfigFastest,
	}
}

func (kc *KafkaConsumer) Start(ctx context.Context) {
	go func() {

		reader := kafka.NewReader(kc.Config)
		defer func() {
			err := reader.Close()
			if err != nil {
				log.Fatalf("closing reader failed with err: %v", err)
			}
		}()

		log.Printf("reader stats: %v", reader.Stats())

		for {
			m, err := reader.ReadMessage(ctx)
			if err != nil {
				log.Printf("kafka read error: %v", err)
				continue
			}
			// m.Time is the Ts when the message is written into kafka
			var msg message.Message
			if err := kc.jsonFast.Unmarshal(m.Value, &msg); err != nil {
				log.Printf("unmarshalling json failed with err: %v", err)
				continue
			}

			kc.ResponseWaiter.Deliver(msg)
		}

	}()
}
