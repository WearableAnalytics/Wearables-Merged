package pkg

import (
	"context"
	"log"
	"sync"

	jsoniter "github.com/json-iterator/go"
	kafka "github.com/segmentio/kafka-go"
)

type KafkaConsumer struct {
	Reader         *kafka.Reader
	ResponseWaiter *ResponseWaiter
	Config         kafka.ReaderConfig
	jsonFast       jsoniter.API
}

type ResponseWaiter struct {
	mu   sync.Mutex
	wait map[string]chan BenchmarkMessage
}

func NewResponseWaiter() *ResponseWaiter {
	return &ResponseWaiter{
		wait: make(map[string]chan BenchmarkMessage),
	}
}

func (rw *ResponseWaiter) Register(msgID string) chan BenchmarkMessage {
	rw.mu.Lock()
	defer rw.mu.Unlock()

	ch := make(chan BenchmarkMessage, 1)
	rw.wait[msgID] = ch
	return ch
}

func (rw *ResponseWaiter) Deliver(msg BenchmarkMessage) {
	rw.mu.Lock()
	ch, exists := rw.wait[msg.MessageID]
	if exists {
		delete(rw.wait, msg.MessageID)
	}

	rw.mu.Unlock()

	if exists {
		ch <- msg
	}
}

func NewKafkaConsumer(rw *ResponseWaiter, topic string, partition int, maxBytes int, brokers ...string) *KafkaConsumer {

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

		for {
			m, err := reader.ReadMessage(ctx)
			if err != nil {
				log.Printf("kafka read error: %v", err)
				continue
			}
			var msg BenchmarkMessage
			if err := kc.jsonFast.Unmarshal(m.Value, &msg); err != nil {
				log.Printf("unmarshalling json failed with err: %v", err)
				continue
			}

			kc.ResponseWaiter.Deliver(msg)
		}

	}()
}
