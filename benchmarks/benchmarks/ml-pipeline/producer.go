package main

import (
	"context"
	"fmt"
	"log"
	"math"
	"sync/atomic"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type Producer struct {
	KafkaProducer  *kafka.Producer
	MessageCounter atomic.Int64

	KafkaConfig
	PayloadConfig
	LoadConfig
}

type KafkaConfig struct {
	KafkaURL string
	Topic    string
}

type PayloadConfig struct {
	MeasurementName string
	Category        string
	BaseDeviceID    string
	Value           int
}

type LoadConfig struct {
	RPS              float64
	RampUpDuration   int
	Duration         int
	RampDownDuration int
	StartRPS         float64 // ramp start; if 0, no ramp (runs at RPS immediately)
	Step             float64 // RPS added per second during ramp; 0 means no ramp
}

func NewLoadConfig(startRPS, rps float64, rampUpDuration, duration, rampDownDuration int) LoadConfig {
	var step float64
	if rampUpDuration > 0 {
		start := startRPS
		if start <= 0 {
			start = 1
		}
		step = (rps - start) / float64(rampUpDuration)
	}

	return LoadConfig{
		RPS:              rps,
		RampUpDuration:   rampUpDuration,
		Duration:         duration,
		RampDownDuration: rampDownDuration,
		StartRPS:         startRPS,
		Step:             step,
	}
}

func NewProducer(kafkaCfg KafkaConfig, payloadCfg PayloadConfig, loadCfg LoadConfig) (*Producer, error) {
	config := &kafka.ConfigMap{
		"bootstrap.servers": kafkaCfg.KafkaURL,
		"security.protocol": "PLAINTEXT",
	}

	kafkaProducer, err := kafka.NewProducer(config)
	if err != nil {
		return nil, err
	}

	return &Producer{
		KafkaProducer:  kafkaProducer,
		MessageCounter: atomic.Int64{},
		KafkaConfig:    kafkaCfg,
		PayloadConfig:  payloadCfg,
		LoadConfig:     loadCfg,
	}, nil
}

// GenerateNewLineProtocol creates a new Message
// goos: darwin
// goarch: arm64
// pkg: ml
// cpu: Apple M2
// BenchmarkGenerateLineProtocol
// BenchmarkGenerateLineProtocol-8   	 3748686	       314.9 ns/op
func (p *Producer) GenerateNewLineProtocol() string {
	ts := time.Now().UTC().UnixMilli()
	messageCount := p.MessageCounter.Add(1)
	lineProtocol := fmt.Sprintf("%s,device-id=%s-%d,category=%s value=%d %d", p.MeasurementName, p.BaseDeviceID, messageCount, p.Category, p.Value, ts)
	return lineProtocol
}

func (p *Producer) Run(ctx context.Context) {
	defer func() {
		p.KafkaProducer.Flush(10_000)
		p.KafkaProducer.Close()
	}()

	go func() {
		for e := range p.KafkaProducer.Events() {
			if m, ok := e.(*kafka.Message); ok {
				if m.TopicPartition.Error != nil {
					log.Printf("delivery failed: %v\n", m.TopicPartition.Error)
				}
			}
		}
	}()

	var rampUpStep, rampDownStep float64
	if p.RampUpDuration > 0 {
		startRPS := p.StartRPS
		if startRPS <= 0 {
			startRPS = 1
		}

		rampUpStep = (p.RPS - startRPS) / float64(p.RampUpDuration)
	}

	if p.RampDownDuration > 0 {
		rampDownStep = p.RPS / float64(p.RampDownDuration)
	}

	totalDuration := time.Duration(p.RampUpDuration+p.Duration+p.RampDownDuration) * time.Second
	rampUpEnd := time.Duration(p.RampUpDuration) * time.Second
	rampDownStart := time.Duration(p.RampUpDuration+p.Duration) * time.Second

	start := time.Now()
	end := start.Add(totalDuration)

	currentRPS := p.StartRPS
	if p.RampUpDuration == 0 || currentRPS <= 0 {
		currentRPS = p.RPS
	}

	interval, batch := calculateInterval(currentRPS)
	subTicker := time.NewTicker(interval)
	defer subTicker.Stop()

	rampTicker := time.NewTicker(time.Second)
	defer rampTicker.Stop()

	produce := func() {
		lineProtocol := []byte(p.GenerateNewLineProtocol())

		msg := kafka.Message{
			TopicPartition: kafka.TopicPartition{
				Topic:     &p.Topic,
				Partition: kafka.PartitionAny,
			},
			Value: lineProtocol,
		}

		err := p.KafkaProducer.Produce(&msg, nil)
		if err != nil {
			log.Printf("produce error: %v", err)
		}
	}

	updateSubTicker := func(newRPS float64) {
		newInterval, newBatch := calculateInterval(newRPS)
		batch = newBatch
		subTicker.Stop()
		subTicker = time.NewTicker(newInterval)
	}

	for time.Now().Before(end) {
		select {
		case <-ctx.Done():
			return
		case <-rampTicker.C:
			elapsed := time.Since(start)

			switch {
			case elapsed < rampUpEnd && rampUpStep > 0:
				currentRPS = math.Min(currentRPS+rampUpStep, p.RPS)
				updateSubTicker(currentRPS)
			case elapsed >= rampDownStart && rampDownStep > 0:
				currentRPS = math.Max(currentRPS-rampDownStep, 0)
				if currentRPS == 0 {
					return
				}
				updateSubTicker(currentRPS)
			}
		case <-subTicker.C:
			for range batch {
				produce()
			}
		}
	}
}

// calculateInterval returns the tick interval and how many messages to send per tick.
// Above ~1000RPS a single ticker can't keep up.
func calculateInterval(rps float64) (time.Duration, int) {
	if rps <= 0 {
		return time.Second, 0
	}

	const maxTicksPerSec = 1000
	if rps <= maxTicksPerSec {
		return time.Duration(float64(time.Second) / rps), 1
	}

	batch := int(math.Ceil(rps / maxTicksPerSec))
	return time.Millisecond, batch
}
