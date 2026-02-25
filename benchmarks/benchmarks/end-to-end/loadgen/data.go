package main

import (
	"encoding/json"
	"time"
)

type Provider struct {
	MessageSize     int
	TimestampLayout string
	tracker         *Tracker
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

func (p *Provider) CreateBenchmarkMessage() Payload {
	now := time.Now().UTC()

	payload := Payload{
		DeviceInfo: DeviceInfo{
			Platform:           "android",
			DeviceId:           "",
			AuthorizationToken: "",
		},
		BatchInfo: BatchInfo{
			CollectionStart: now.Format(p.TimestampLayout),
			CollectionEnd:   now.Format(p.TimestampLayout),
			LastSendTime:    now.Format(p.TimestampLayout),
		},
		Measurements: Measurements{
			Instantaneous: make([]InstantMeasurement, 0),
			Cumulative:    make([]CumulativeMeasurement, 0),
			Duration:      make([]DurationMeasurement, 0),
		},
		SourceName:      "mobile-client",
		SourcePlatform:  "android",
		TotalStepsToday: 20000,
		Timestamp:       now.Format(p.TimestampLayout),
	}

	base := p.tracker.MessageCounter.Add(1)

	for {
		instant := InstantMeasurement{
			Type:      "heart-rate",
			Value:     float32(base),
			Unit:      "BEATS_PER_MINUTE",
			Timestamp: now.Format(p.TimestampLayout),
		}

		payload.Measurements.Instantaneous = append(payload.Measurements.Instantaneous, instant)

		data, _ := json.Marshal(payload)
		if len(data) >= p.MessageSize {
			break
		}
	}

	return payload
}

func (p *Provider) GetData() Payload {
	return p.CreateBenchmarkMessage()
}

func NewProvider(msgSize int, tracker *Tracker) *Provider {
	layout := "2006-01-02T15:04:05.000"
	return &Provider{
		MessageSize:     msgSize,
		TimestampLayout: layout,
		tracker:         tracker,
	}
}
