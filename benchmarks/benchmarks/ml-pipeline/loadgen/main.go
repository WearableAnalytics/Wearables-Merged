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
	influxURL        string
	influxToken      string
	influxOrg        string
	influxBucket     string
	rampUpDuration   int
	duration         int
	rampDownDuration int
	RPS              int
	startRPS         int
)

func loadConfig() {
	kafkaURL = mustGetEnvString("KAFKA_URL")
	kafkaTopic = mustGetEnvString("TOPIC")
	influxURL = mustGetEnvString("INFLUX_URL")
	influxToken = mustGetEnvString("INFLUX_TOKEN")
	influxOrg = mustGetEnvString("INFLUX_ORG")
	influxBucket = mustGetEnvString("INFLUX_BUCKET")

	rampUpDuration = mustGetEnvInt("RAMP_UP_DURATION")
	rampDownDuration = mustGetEnvInt("RAMP_DOWN_DURATION")
	duration = mustGetEnvInt("DURATION")

	RPS = mustGetEnvInt("RPS")
	startRPS = mustGetEnvInt("START_RPS")
}

func main() {
	loadConfig()
	log.SetFlags(log.LUTC)
	startTime := time.Now().UTC()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGTERM, syscall.SIGINT)
	go func() {
		<-sigs
		cancel()
	}()

	loadCfg := NewLoadConfig(float64(startRPS), float64(RPS), rampUpDuration, duration, rampDownDuration)

	kafkaCfg := KafkaConfig{
		KafkaURL: kafkaURL,
		Topic:    kafkaTopic,
	}

	payloadCfg := PayloadConfig{
		MeasurementName: "heart-rate",
		Category:        "measurements.instantaneous",
		BaseDeviceID:    "benchmark-client",
		Value:           72,
	}

	p, err := NewProducer(kafkaCfg, payloadCfg, loadCfg)
	if err != nil {
		log.Fatalf("failed to create producer: %v", err)
	}
	p.Run(ctx)

	// Pipeline needs ~30s to process a message, therefore sleep!
	time.Sleep(1 * time.Minute)

	obsCtx, obsCancel := context.WithCancel(context.Background())
	defer obsCancel()

	observer := NewObserver(influxURL, influxToken, influxOrg, influxBucket, startTime)
	log.Printf("now starting observing with: %v", observer)
	observer.Run(obsCtx)
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
