package main

import (
	"log"
	"os"
	"strconv"
	"time"

	lg "github.com/luccadibe/go-loadgen"
)

var (
	serviceURL       string
	messageSize      int
	rampUpDuration   int
	duration         int // seconds
	rampDownDuration int
	RPS              int
)

func init() {
	// Logger konfigurieren
	log.SetOutput(os.Stderr)
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	log.SetPrefix("ingestion-service-lg: ")

	// Konfiguration laden
	serviceURL = mustGetEnvString("SERVICE_URL")
	messageSize = mustGetEnvInt("MESSAGE_SIZE")
	rampUpDuration = mustGetEnvInt("RAMP_UP_DURATION")
	duration = mustGetEnvInt("DURATION")
	rampDownDuration = mustGetEnvInt("RAMP_DOWN_DURATION")
	RPS = mustGetEnvInt("RPS")
}

func main() {
	collector := NewCollector()
	provider := NewProvider(messageSize)
	client := NewClient(serviceURL)

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
	ew.Run()
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
