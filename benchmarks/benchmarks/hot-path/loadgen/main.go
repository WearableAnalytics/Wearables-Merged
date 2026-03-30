package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

var (
	serviceUrl       string
	jwtToken         string
	messageSize      int
	rampUpDuration   int
	duration         int
	rampDownDuration int
	rps              int
)

func loadConfig() {
	serviceUrl = mustGetEnvString("SERVICE_URL")
	jwtToken = mustGetEnvString("JWT_TOKEN")
	messageSize = mustGetEnvInt("MESSAGE_SIZE")
	rampUpDuration = mustGetEnvInt("RAMP_UP_DURATION")
	duration = mustGetEnvInt("DURATION")
	rampDownDuration = mustGetEnvInt("RAMP_DOWN_DURATION")
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

	dp := NewDataProvider(messageSize)
	c := &Client{
		Addr:       serviceUrl,
		AuthToken:  jwtToken,
		HttpClient: &http.Client{},
	}

	var phases []Phase

	if rampUpDuration > 0 {
		phases = append(phases, Phase{
			Type:     1,
			Duration: time.Duration(rampUpDuration) * time.Second,
			StartRPS: 0,
			Step:     rps / rampUpDuration,
		})
	}

	if duration > 0 {
		phases = append(phases, Phase{
			Type:     0,
			Duration: time.Duration(duration) * time.Second,
			StartRPS: rps,
			Step:     0,
		})
	}

	if rampDownDuration > 0 {
		phases = append(phases, Phase{
			Type:     2,
			Duration: time.Duration(rampDownDuration) * time.Second,
			StartRPS: rps,
			Step:     rps / rampDownDuration,
		})
	}

	producer := Producer{
		Client:   c,
		Provider: dp,
		Phases:   phases,
	}

	producer.Run(ctx)
}
