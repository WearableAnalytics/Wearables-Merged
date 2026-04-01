package main

import (
	"encoding/json"
	"log"
	"sync/atomic"
	"time"
)

type Provider struct {
	MessageCount    atomic.Int32
	MessageSize     int
	TimestampLayout string
}

type Payload struct {
	DeviceInfo      DeviceInfo   `json:"deviceInfo"`
	BatchInfo       BatchInfo    `json:"batchInfo"`
	Measurements    Measurements `json:"measurements"`
	SourceName      string       `json:"sourceName"`
	SourcePlatform  string       `json:"sourcePlatform,omitempty"`
	TotalStepsToday int          `json:"totalStepsToday,omitempty"`
	Timestamp       string       `json:"timestamp"`
}

type DeviceInfo struct {
	Platform           string `json:"platform"`
	DeviceId           string `json:"deviceId"`
	AuthorizationToken string `json:"authorizationToken,omitempty"`
}

type BatchInfo struct {
	CollectionStart string `json:"collectionStart"`
	CollectionEnd   string `json:"collectionEnd"`
	LastSendTime    string `json:"lastSendTime,omitempty"`
}

type Measurements struct {
	Instantaneous []InstantMeasurement    `json:"instantaneous"`
	Cumulative    []CumulativeMeasurement `json:"cumulative"`
	Duration      []DurationMeasurement   `json:"duration"`
}

type InstantMeasurement struct {
	Type      string  `json:"type"`
	Value     float32 `json:"value"`
	Unit      string  `json:"unit"`
	Timestamp string  `json:"timestamp"`
}
type CumulativeMeasurement struct {
	Type        string  `json:"type"`
	Value       float32 `json:"value"`
	Unit        string  `json:"unit"`
	PeriodStart string  `json:"periodStart"`
	PeriodEnd   string  `json:"periodEnd"`
	Duration    int     `json:"duration"`
}
type DurationMeasurement struct {
	Type            string  `json:"type"`
	Value           float32 `json:"value"`
	Unit            string  `json:"unit"`
	StartTime       string  `json:"startTime"`
	EndTime         string  `json:"endTime"`
	DurationMinutes int     `json:"durationMinutes"`
}

func NewDataProvider(messageSize int) *Provider {
	return &Provider{
		MessageCount:    atomic.Int32{},
		MessageSize:     messageSize,
		TimestampLayout: "2006-01-02T15:04:05.000",
	}
}

func (p *Provider) CreateBenchmarkMessage() Payload {
	now := time.Now().UTC().Format(p.TimestampLayout)
	log.Println(now)

	payload := Payload{
		DeviceInfo: DeviceInfo{
			Platform:           "android",
			DeviceId:           "",
			AuthorizationToken: "",
		},
		BatchInfo: BatchInfo{
			CollectionStart: now,
			CollectionEnd:   now,
			LastSendTime:    now,
		},
		Measurements: Measurements{
			Instantaneous: make([]InstantMeasurement, 0),
			Cumulative:    make([]CumulativeMeasurement, 0),
			Duration:      make([]DurationMeasurement, 0),
		},
		SourceName:      "mobile-client",
		SourcePlatform:  "android",
		TotalStepsToday: 20000,
		Timestamp:       now,
	}

	instant := InstantMeasurement{
		Type:      "heart-rate",
		Value:     72,
		Unit:      "BEATS_PER_MINUTE",
		Timestamp: now,
	}

	instantBytes, _ := json.Marshal(instant)
	payload.Measurements.Instantaneous = append(payload.Measurements.Instantaneous, instant)

	payloadBytes, _ := json.Marshal(payload)

	n := (p.MessageSize - len(payloadBytes)) / len(instantBytes)

	for i := 0; i < n+1; i++ {
		instant = InstantMeasurement{
			Type:      "heart-rate",
			Value:     72,
			Unit:      "BEATS_PER_MINUTE",
			Timestamp: now,
		}

		payload.Measurements.Instantaneous = append(payload.Measurements.Instantaneous, instant)
	}

	return payload
}
