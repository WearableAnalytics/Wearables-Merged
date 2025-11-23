package example

import (
	"fmt"
	"math/rand"
	"strconv"
	"time"
	"unsafe"
)

type ExampleProvider struct {
	MaxSize           int // in bytes
	DeviceCount       int
	BaseDeviceInfo    DeviceInfo
	BaseInstantaneous Instantaneous
	BaseCumulative    Cumulative
	BaseDuration      Duration
	SourceName        string
}

type Message struct {
	DeviceInfo      DeviceInfo   `json:"deviceInfo,omitempty"`
	BatchInfo       BatchInfo    `json:"batchInfo,omitempty"`
	Measurements    Measurements `json:"measurements,omitempty"`
	SourceName      string       `json:"sourceName,omitempty"`
	TotalStepsToday interface{}  `json:"totalStepsToday,omitempty"`
	Timestamp       string       `json:"timestamp,omitempty"`
}

type Response struct {
	Err     error
	Latency time.Duration
}

func (r Response) CSVHeaders() []string {
	return []string{"errors", "latency"}
}

func (r Response) CSVRecord() []string {
	return []string{r.Err.Error(), r.Latency.String()}
}

type DeviceInfo struct {
	Platform           string `json:"platform,omitempty"`
	DeviceID           string `json:"deviceID,omitempty"`
	AuthorizationToken string `json:"authorizationToken,omitempty"`
}

type BatchInfo struct {
	// Timestamps
	CollectionStart string `json:"collectionStart,omitempty"`
	CollectionEnd   string `json:"collectionEnd,omitempty"`
}

type Measurements struct {
	Instantaneous []Instantaneous `json:"instantaneous,omitempty"`
	Cumulative    []Cumulative    `json:"cumulative,omitempty"`
	Duration      []Duration      `json:"duration,omitempty"`
}

type Instantaneous struct {
	Type      string `json:"type,omitempty"`
	Value     int    `json:"value,omitempty"`
	Unit      string `json:"unit,omitempty"`
	Timestamp string `json:"timestamp,omitempty"`
}

type Cumulative struct {
	Type  string `json:"type,omitempty"`
	Value int    `json:"value,omitempty"`
	Unit  string `json:"unit,omitempty"`
	// Time
	PeriodStart string `json:"periodStart,omitempty"`
	PeriodEnd   string `json:"periodEnd,omitempty"`
	Duration    int    `json:"duration,omitempty"` //sec
}

type Duration struct{}

func NewExampleProvider(deviceCount int, maxSize int) *ExampleProvider {
	var provider ExampleProvider

	provider.DeviceCount = deviceCount
	provider.MaxSize = maxSize

	// BaseDeviceInfo
	platform := "iOS"
	authorizationToken := "testToken"
	provider.BaseDeviceInfo = DeviceInfo{
		Platform:           platform,
		AuthorizationToken: authorizationToken,
	}

	// Currently only Steps
	cumulativeType := "STEPS"
	cumulativeUnit := "COUNT"
	provider.BaseCumulative = Cumulative{
		Type: cumulativeType,
		Unit: cumulativeUnit,
	}

	provider.SourceName = "Test iPhone"
	return &provider
}

func (e ExampleProvider) GetData() Message {
	// Calculate values
	e.BaseDeviceInfo.DeviceID = fmt.Sprintf("test-device-%s", strconv.Itoa(rand.Intn(e.DeviceCount)))
	collectionStart := time.Now().Add(-15 * time.Minute)
	collectionEnd := time.Now()

	instantaneous := e.GenerateInstantaneous()
	cumulative := e.GenerateCumulative(collectionStart, collectionEnd, e.MaxSize/3)
	duration := e.GenerateDuration()

	return Message{
		DeviceInfo: e.BaseDeviceInfo,
		BatchInfo: BatchInfo{
			collectionStart.Format(time.RFC3339),
			collectionEnd.Format(time.RFC3339)},
		Measurements: Measurements{
			Instantaneous: instantaneous,
			Cumulative:    cumulative,
			Duration:      duration,
		},
		SourceName:      e.SourceName,
		TotalStepsToday: nil,
		Timestamp:       collectionEnd.Format(time.RFC3339),
	}
}

func (e ExampleProvider) GenerateInstantaneous() []Instantaneous {
	return []Instantaneous{}
}

func (e ExampleProvider) GenerateDuration() []Duration {
	return []Duration{}
}

func (e ExampleProvider) GenerateCumulative(start time.Time, end time.Time, maxSize int) []Cumulative {
	var cumulatives []Cumulative
	duration := end.Sub(start).Minutes()
	approx := duration / float64(len(cumulatives))

	base := e.BaseCumulative
	size := 0
	i := 0
	for {
		periodStart := start
		if i > 0 {
			periodStart, _ = time.Parse(time.RFC3339, cumulatives[i-1].PeriodEnd)
		}

		periodDuration := time.Duration(approx * (rand.Float64() + 0.5))
		periodEnd := periodStart.Add(periodDuration * time.Second)

		if !periodStart.Add(periodDuration).Before(end) {
			periodEnd = end
			periodDuration = periodEnd.Sub(periodStart)
			break
		}

		// the longer the duration the higher is the value
		value := rand.Intn(100) * int(duration/100)

		cumulative := Cumulative{
			Type:        base.Type,
			Value:       value,
			Unit:        base.Unit,
			PeriodStart: periodStart.Format(time.RFC3339),
			PeriodEnd:   periodEnd.Format(time.RFC3339),
			Duration:    int(periodDuration.Seconds()),
		}

		cumulatives = append(cumulatives, cumulative)

		size += int(unsafe.Sizeof(cumulative))
		if size >= maxSize {
			break
		}

		i++
	}

	return cumulatives
}
