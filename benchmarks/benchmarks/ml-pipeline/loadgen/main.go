package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"
)

var (
	kafkaURL         string
	kafkaTopic       string
	rampUpDuration   int
	duration         int
	rampDownDuration int
	RPS              int
	startRPS         int
)

func loadConfig() {
	kafkaURL = mustGetEnvString("KAFKA_URL")
	kafkaTopic = mustGetEnvString("TOPIC")

	rampUpDuration = mustGetEnvInt("RAMP_UP_DURATION")
	rampDownDuration = mustGetEnvInt("RAMP_DOWN_DURATION")
	duration = mustGetEnvInt("DURATION")

	RPS = mustGetEnvInt("RPS")
	startRPS = mustGetEnvInt("START_RPS")
}

func main() {
	loadConfig()
	log.SetFlags(log.LUTC)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGTERM, syscall.SIGINT)
	go func() {
		<-sigs
		cancel()
	}()

	var phases []Phase

	if rampUpDuration > 0 {
		phases = append(phases, Phase{
			Type:     2,
			Duration: time.Duration(rampUpDuration) * time.Second,
			StartRPS: startRPS,
			Step:     RPS / rampUpDuration,
		})
	}
	if duration > 0 {
		phases = append(phases, Phase{
			Type:     1,
			Duration: time.Duration(duration) * time.Second,
			StartRPS: RPS,
			Step:     0,
		})
	}
	if rampDownDuration > 0 {
		phases = append(phases, Phase{
			Type:     3,
			Duration: time.Duration(rampDownDuration) * time.Second,
			StartRPS: RPS,
			Step:     RPS / rampDownDuration,
		})
	}

	kafkaCfg := KafkaConfig{
		KafkaURL: kafkaURL,
		Topic:    kafkaTopic,
	}

	payloadCfg := PayloadConfig{
		MeasurementName: "heart-rate",
		Category:        "measurements.instantaneous",
		BaseDeviceID:    "benchmark-client",
		Value:           72,
		ClientIndex:     0,
		NumClients:      1,
	}

	p, err := NewProducer(kafkaCfg, payloadCfg, phases)
	if err != nil {
		log.Fatalf("failed to create producer: %v", err)
	}
	p.Run(ctx)
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
