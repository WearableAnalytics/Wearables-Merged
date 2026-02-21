package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	lg "github.com/luccadibe/go-loadgen"
)

var (
	serviceURL       string
	influxURL        string
	influxToken      string
	influxOrg        string
	influxBucket     string
	jwtToken         string
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
	jwtToken = mustGetEnvString("JWT_TOKEN")
	messageSize = mustGetEnvInt("MESSAGE_SIZE")
	rampUpDuration = mustGetEnvInt("RAMP_UP_DURATION")
	duration = mustGetEnvInt("DURATION")
	rampDownDuration = mustGetEnvInt("RAMP_DOWN_DURATION")
	RPS = mustGetEnvInt("RPS")
}

func main() {
	log.SetFlags(log.LUTC)
	startTime := time.Now().UTC()
	log.Println("Starting Benchmark now: ", startTime)
	ctx, cancel := context.WithCancel(context.Background())

	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGTERM, syscall.SIGINT)

	go func() {
		<-sigs
		cancel()
	}()

	tracker := NewTracker()

	provider := NewProvider(messageSize, tracker)
	client := NewClient(serviceURL, jwtToken)
	collector := Collector{tracker: tracker}

	conf := &InfluxObserverConfig{
		Addr:       influxURL,
		Token:      influxToken,
		Org:        influxOrg,
		Bucket:     influxBucket,
		WindowSize: 10 * time.Millisecond,
		T0:         startTime,
	}

	obs := NewInfluxObserver(conf, tracker)

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

	ew.Run()
	log.Printf("finished running in: %vs, now sleeping 60s", time.Since(startTime).Seconds())
	time.Sleep(60 * time.Second)
	log.Printf("now starting to observe")
	obs.ObserveBenchmark(ctx)
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
