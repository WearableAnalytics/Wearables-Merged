package message

import (
	"fmt"
	"math/rand"
	"time"

	"github.com/google/uuid"
)

type Provider struct {
	MaxSize           int // in bytes
	DeviceCount       int
	BaseDeviceInfo    DeviceInfo
	BaseInstantaneous Instantaneous
	BaseCumulative    Cumulative
	BaseDuration      Duration
	SourceName        string
}

func NewProvider(deviceCount int, maxSize int) *Provider {
	var provider Provider

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

func (e Provider) GetData() Message {
	// Calculate values
	deviceID := uuid.New().String()
	e.BaseDeviceInfo.DeviceID = fmt.Sprintf("test-device-%s", deviceID)
	collectionStart := time.Now().Add(-15 * time.Minute)
	collectionEnd := time.Now()

	instantaneous := e.GenerateInstantaneous()
	cumulative := e.GenerateCumulative(collectionStart, collectionEnd, e.MaxSize/3)
	duration := e.GenerateDuration()

	return Message{
		DeviceInfo: e.BaseDeviceInfo,
		BatchInfo: BatchInfo{
			fmt.Sprintf("%sZ", collectionStart.Format(time.RFC3339)),
			fmt.Sprintf("%sZ", collectionEnd.Format(time.RFC3339))},
		Measurements: Measurements{
			Instantaneous: instantaneous,
			Cumulative:    cumulative,
			Duration:      duration,
		},
		SourceName:      e.SourceName,
		TotalStepsToday: nil,
		Timestamp:       fmt.Sprintf("%sZ", collectionEnd.Format(time.RFC3339)),
	}
}

func (e Provider) GenerateInstantaneous() []Instantaneous {
	return []Instantaneous{}
}

func (e Provider) GenerateDuration() []Duration {
	return []Duration{}
}

func (e Provider) GenerateCumulative(start time.Time, end time.Time, maxSize int) []Cumulative {
	var cumulatives []Cumulative
	totalDuration := end.Sub(start)
	approx := totalDuration / 10

	base := e.BaseCumulative
	size := 0

	currentStart := start

	typeLen := len(base.Type)
	unitLen := len(base.Unit)

	for size < maxSize && currentStart.Before(end) {
		// Randomize period duration around approx (50%–150%)
		randomFactor := 0.5 + rand.Float64()
		periodDuration := time.Duration(float64(approx) * randomFactor)
		periodEnd := currentStart.Add(periodDuration)

		// Clamp to end time
		if periodEnd.After(end) {
			periodEnd = end
			periodDuration = periodEnd.Sub(currentStart)
		}

		// Compute value proportional to duration
		value := int(float64(rand.Intn(100)) * (totalDuration.Minutes() / 100))

		cumulative := Cumulative{
			Type:        base.Type,
			Value:       value,
			Unit:        base.Unit,
			PeriodStart: currentStart.Format(time.RFC3339),
			PeriodEnd:   periodEnd.Format(time.RFC3339),
			Duration:    int(periodDuration.Seconds()),
		}

		cumulatives = append(cumulatives, cumulative)

		// To avoid json marshalling
		size += typeLen + unitLen + len(cumulative.PeriodStart) + len(cumulative.PeriodEnd) + 8*2 + 8

		currentStart = periodEnd
	}

	return cumulatives
}
