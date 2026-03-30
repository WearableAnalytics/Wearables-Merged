package main

import (
	"context"
	"fmt"
	"log"
	"sync/atomic"
	"time"

	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
)

type Producer struct {
	KafkaProducer  *kafka.Producer
	MessageCounter atomic.Int32

	Phases []Phase
	KafkaConfig
	PayloadConfig
}

type KafkaConfig struct {
	KafkaURL string
	Topic    string
}

var (
	Constant = 1
	RampUp   = 2
	RampDown = 3
)

type Phase struct {
	Type     int
	Duration time.Duration
	StartRPS int
	Step     int

	startTime time.Time
}

type PayloadConfig struct {
	MeasurementName string
	Category        string
	BaseDeviceID    string
	Value           int
	ClientIndex     int
	NumClients      int
}

func NewProducer(kafkaCfg KafkaConfig, payloadCfg PayloadConfig, phases []Phase) (*Producer, error) {
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
		MessageCounter: atomic.Int32{},
		Phases:         phases,
		KafkaConfig:    kafkaCfg,
		PayloadConfig:  payloadCfg,
	}, nil
}

func (p *Phase) CalculateRps() int {
	var rps int
	if p.Type == Constant {
		rps = p.StartRPS
	}
	if p.Type == RampUp {
		rps = int(time.Since(p.startTime).Seconds())*p.Step + p.StartRPS
	}
	if p.Type == RampDown {
		rps = p.StartRPS - int(time.Since(p.startTime).Seconds())*p.Step
	}

	if rps > 1000 {
		rps = 1000
	}
	if rps < 0 {
		rps = 0
	}

	return rps
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

	for _, phase := range p.Phases {
		p.executePhase(ctx, &phase)
	}
}

func (p *Producer) executePhase(ctx context.Context, phase *Phase) {
	phase.startTime = time.Now()
	timer, ticker := time.NewTimer(phase.Duration), time.NewTicker(1*time.Second)

	for {
		select {
		case <-ctx.Done():
			return
		case <-timer.C:
			return
		case <-ticker.C:
			n := phase.CalculateRps()

			tick := time.Duration(1000/n) * time.Millisecond

			subTicker := time.NewTicker(tick)

			log.Printf("[%ds] sending %d msg/s", int(time.Since(phase.startTime).Seconds()), n)

			for i := 0; i < n; i++ {
				<-subTicker.C
				go p.Produce()
			}

		}
	}
}

func (p *Producer) Produce() {
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
		log.Println(err)
	}
}

func (p *Producer) GenerateNewLineProtocol() string {
	ts := time.Now().UTC().UnixNano()

	deviceID := p.CalculateDeviceID()

	lineProtocol := fmt.Sprintf("%s,device-id=%s-%d,category=%s,version=1.0.0 value=%d %d", p.MeasurementName, p.BaseDeviceID, deviceID, p.Category, p.Value, ts)
	return lineProtocol
}

func (p *Producer) CalculateDeviceID() int32 {
	messageCount := p.MessageCounter.Add(1)
	return messageCount
}
