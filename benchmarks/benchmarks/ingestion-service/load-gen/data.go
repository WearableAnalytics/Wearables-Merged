package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

type Provider struct {
	Payload        Payload
	MessageCounter atomic.Uint32
}

type Collector struct {
	writer         *csv.Writer
	headersWritten bool
	mu             *sync.Mutex
}

type Result struct {
	MessageID         string
	StatusCode        int
	SendTimestamp     string
	ReceivedTimestamp string
}

type Payload struct {
	DeviceInfo      DeviceInfo   `json:"deviceInfo"`
	BatchInfo       BatchInfo    `json:"batchInfo"`
	Measurements    Measurements `json:"measurements"`
	SourceName      string       `json:"sourceName"`
	SourcePlatform  string       `json:"sourcePlatform,omitempty"`
	TotalStepsToday int          `json:"totalStepsToday,omitempty"`
	Timestamp       time.Time    `json:"timestamp"`
}

type DeviceInfo struct {
	Platform           string `json:"platform"`
	DeviceId           string `json:"deviceId"`
	AuthorizationToken string `json:"authorizationToken,omitempty"`
}

type BatchInfo struct {
	CollectionStart time.Time `json:"collectionStart"`
	CollectionEnd   time.Time `json:"collectionEnd"`
	LastSendTime    time.Time `json:"lastSendTime,omitempty"`
}

type Measurements struct {
	Instantaneous []InstantMeasurement    `json:"instantaneous"`
	Cumulative    []CumulativeMeasurement `json:"cumulative"`
	Duration      []DurationMeasurement   `json:"duration"`
}

type InstantMeasurement struct {
	Type      string    `json:"type"`
	Value     float32   `json:"value"`
	Unit      string    `json:"unit"`
	Timestamp time.Time `json:"timestamp"`
}
type CumulativeMeasurement struct {
	Type        string    `json:"type"`
	Value       float32   `json:"value"`
	Unit        string    `json:"unit"`
	PeriodStart time.Time `json:"periodStart"`
	PeriodEnd   time.Time `json:"periodEnd"`
	Duration    int       `json:"duration"`
}
type DurationMeasurement struct {
	Type            string    `json:"type"`
	Value           float32   `json:"value"`
	Unit            string    `json:"unit"`
	StartTime       time.Time `json:"startTime"`
	EndTime         time.Time `json:"endTime"`
	DurationMinutes int       `json:"durationMinutes"`
}

func CreateBenchmarkMessage(now time.Time, size int) Payload {
	payload := Payload{
		DeviceInfo: DeviceInfo{
			Platform:           "android",
			AuthorizationToken: "v4z1hnhocqfbn580bncß8qb",
		},
		BatchInfo: BatchInfo{
			CollectionStart: now.Add(-10 * time.Minute),
			CollectionEnd:   now,
			LastSendTime:    now.Add(-30 * time.Second),
		},
		Measurements: Measurements{
			Instantaneous: make([]InstantMeasurement, 0, 16),
			Cumulative:    make([]CumulativeMeasurement, 0, 16),
			Duration:      make([]DurationMeasurement, 0, 16),
		},
		SourceName:      "mobile-client",
		SourcePlatform:  "android",
		TotalStepsToday: 20000,
		Timestamp:       now,
	}

	instantaneous := InstantMeasurement{
		Type:      "heart-rate",
		Value:     72,
		Unit:      "bpm",
		Timestamp: now,
	}

	cumulative := CumulativeMeasurement{
		Type:        "steps",
		Value:       120,
		Unit:        "count",
		PeriodStart: now.Add(-1 * time.Minute),
		PeriodEnd:   now,
		Duration:    60,
	}

	duration := DurationMeasurement{
		Type:            "sleep",
		Value:           1,
		Unit:            "session",
		StartTime:       now.Add(-8 * time.Hour),
		EndTime:         now,
		DurationMinutes: 60 * 8,
	}

	data, _ := json.Marshal(payload)

	for len(data) < size {
		payload.Measurements.Instantaneous = append(payload.Measurements.Instantaneous, instantaneous)
		payload.Measurements.Cumulative = append(payload.Measurements.Cumulative, cumulative)
		payload.Measurements.Duration = append(payload.Measurements.Duration, duration)

		data, _ = json.Marshal(payload)
	}

	return payload
}

func NewProvider(msgSize int) *Provider {
	return &Provider{
		Payload: CreateBenchmarkMessage(time.Now(), msgSize),
	}
}

func (p *Provider) GetData() Payload {
	p.Payload.DeviceInfo.DeviceId = fmt.Sprintf("%d", p.MessageCounter.Add(1))
	return p.Payload
}

func NewCollector() *Collector {
	return &Collector{
		writer:         csv.NewWriter(os.Stdout),
		headersWritten: false,
		mu:             &sync.Mutex{},
	}
}

func (c *Collector) Collect(result Result) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if !c.headersWritten {
		if err := c.writer.Write(result.CSVHeaders()); err != nil {
			log.Printf("failed to write CSV header: %v", err)
			return
		}

		c.headersWritten = true
	} else {
		if err := c.writer.Write(result.CSVRecord()); err != nil {
			log.Printf("failed to write CSV record: %v", err)
		}
	}
}

func (c *Collector) Close() {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.writer.Flush()
	if err := c.writer.Error(); err != nil {
		log.Printf("failed to flush CSV writer: %v", err)
	}
}

func (r Result) CSVHeaders() []string {
	return []string{
		"message-id",
		"status-code",
		"t_send",
		"t_received",
	}
}

func (r Result) CSVRecord() []string {
	return []string{
		r.MessageID,
		strconv.Itoa(r.StatusCode),
		r.SendTimestamp,
		r.ReceivedTimestamp,
	}
}
