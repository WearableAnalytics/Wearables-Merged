package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

var (
	kafkaURL         string
	topic            string
	messageSize      int
	rampUpDuration   int
	duration         int
	rampDownDuration int
	rps              int
)

func init() {
	kafkaURL = mustGetEnvString("KAFKA_URL")
	topic = mustGetEnvString("TOPIC")
	messageSize = mustGetEnvInt("MESSAGE_SIZE")
	rampUpDuration = mustGetEnvInt("RAMP_UP_DURATION")
	duration = mustGetEnvInt("DURATION")
	rampDownDuration = mustGetEnvInt("RAMP_DOWN_DURATION")
	rps = mustGetEnvInt("RPS")
}

func main() {
	provider := NewProvider(messageSize)

	producer, err := kafka.NewProducer(&kafka.ConfigMap{
		"bootstrap.servers": kafkaURL,
	})
	if err != nil {
		log.Fatalf("test: %v", err)
	}
	defer producer.Close()

	go func() {
		for e := range producer.Events() {
			if m, ok := e.(*kafka.Message); ok {
				if m.TopicPartition.Error != nil {
					log.Printf("delivery failed: %v\n", m.TopicPartition.Error)
				}
			}
		}
	}()

	consumerTopic := "wearables-lp"
	consumer, err := kafka.NewConsumer(&kafka.ConfigMap{
		"bootstrap.servers": kafkaURL,
		"group.id":          "bench-consumer",
	})

	if err != nil {
		log.Fatalf("consumer: %v", err)
	}
	defer consumer.Close()

	if err := consumer.Subscribe(consumerTopic, nil); err != nil {
		log.Fatalf("subscribe: %v", err)
	}

	go func() {
		time.Sleep(1 * time.Second)
		log.Printf("message-id,t_produced,t_published,t_observed")
		for {
			msg, err := consumer.ReadMessage(-1)
			if err != nil {
				continue
			}

			tProducedStr, ok := getHeader(msg.Headers, "t_produced")
			if !ok {
				continue
			}

			tPublished := fmt.Sprintf("%d", msg.Timestamp.UnixNano())

			messageId, ok := getHeader(msg.Headers, "message-id")
			if !ok {
				continue
			}

			tObserved := fmt.Sprintf("%d", time.Now().UnixNano())

			log.Printf("%s,%s,%s,%s", messageId, tProducedStr, tPublished, tObserved)
		}
	}()

	payload, _ := json.Marshal(provider.GetData())

	ticker := time.NewTicker(time.Second / time.Duration(rps))
	defer ticker.Stop()

	end := time.Now().Add(time.Duration(duration) * time.Second)

	var msgID int64

	log.Printf("now staring producer")
	for time.Now().Before(end) {
		<-ticker.C
		msgID++

		now := time.Now().UnixNano()

		headers := []kafka.Header{
			{Key: "message-id", Value: []byte(strconv.FormatInt(msgID, 10))},
			{Key: "t_produced", Value: []byte(strconv.FormatInt(now, 10))},
		}

		msg := kafka.Message{
			TopicPartition: kafka.TopicPartition{
				Topic:     &topic,
				Partition: kafka.PartitionAny,
			},
			Value:   payload,
			Headers: headers,
		}

		err := producer.Produce(&msg, nil)
		if err != nil {
			log.Printf("produce error: %v", err)
		}
	}

	producer.Flush(10_000)
}

func mustGetEnvString(key string) string {
	value := os.Getenv(key)
	if value == "" {
		log.Fatalf("env var %s is not set or empty", key)
	}
	return value
}

func mustGetEnvInt(key string) int {
	value := os.Getenv(key)
	if value == "" {
		log.Fatalf("env var %s is not set", key)
	}

	i, err := strconv.Atoi(value)
	if err != nil {
		log.Fatalf("env var %s must be an integer: %v", key, err)
	}
	return i
}

func getHeader(headers []kafka.Header, key string) (string, bool) {
	for _, h := range headers {
		if h.Key == key {
			return string(h.Value), true
		}
	}

	return "", false
}
