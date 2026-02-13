package main

import (
	"context"
	"log"
	"os"
	"strconv"
	"time"

	lg "github.com/luccadibe/go-loadgen"
)

var (
	serviceURL       string
	influxURL        string
	influxToken      string
	influxOrg        string
	influxBucket     string
	messageSize      int
	rampUpDuration   int
	duration         int // seconds
	rampDownDuration int
	RPS              int
)

func init() {
	serviceURL = mustGetEnvString("SERVICE_URL")
	influxURL = mustGetEnvString("INFLUX_URL")
	influxToken = mustGetEnvString("INFLUX_TOKEN")
	influxOrg = mustGetEnvString("INFLUX_ORG")
	influxBucket = mustGetEnvString("INFLUX_BUCKET")
	messageSize = mustGetEnvInt("MESSAGE_SIZE")
	rampUpDuration = mustGetEnvInt("RAMP_UP_DURATION")
	duration = mustGetEnvInt("DURATION")
	rampDownDuration = mustGetEnvInt("RAMP_DOWN_DURATION")
	RPS = mustGetEnvInt("RPS")
}

func main() {
	provider := NewProvider(messageSize)
	client := NewClient(serviceURL)
	collector := NewCollector()
	conf := &InfluxObserverConfig{
		Addr:       influxURL,
		Token:      influxToken,
		Org:        influxOrg,
		Bucket:     influxBucket,
		WindowSize: 10 * time.Millisecond,
		T0:         time.Now(),
	}

	obs := NewInfluxObserver(conf)

	maxDuration := rampUpDuration + duration + rampDownDuration

	ew, err := lg.NewEndpointWorkload[Payload, Result](
		"Ingestion-Service-Test",
		&lg.Config{
			GenerateWorkload: false,
			MaxDuration:      time.Duration(maxDuration) * time.Second,
			Phases: []lg.TestPhase{
				{
					Name:      "ramp-up",
					Type:      "variable",
					StartTime: 0,
					Duration:  time.Duration(rampUpDuration) * time.Second,
					StartRPS:  0,
					EndRPS:    RPS,
					Step:      0,
				},
				{
					Name:      "stay",
					Type:      "constant",
					StartTime: time.Duration(rampUpDuration) * time.Second,
					Duration:  time.Duration(duration) * time.Second,
					StartRPS:  RPS,
					EndRPS:    RPS,
					Step:      1,
				},
				{
					Name:      "ramp-down",
					Type:      "variable",
					StartTime: (time.Duration(rampUpDuration) + time.Duration(duration)) * time.Second,
					Duration:  time.Duration(rampDownDuration) * time.Second,
					StartRPS:  RPS,
					EndRPS:    0,
					Step:      2,
				},
			},
		},
		client,
		provider,
		collector,
	)
	if err != nil {
		log.Fatalf("not able to start endpoint-workload: %v", err)
	}
	go ew.Run()

	obs.ObserveAndLog(context.Background())
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
