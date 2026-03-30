package main

import (
	"context"
	"log"
	"sync/atomic"
	"testing"
	"time"
)

type mockClient struct {
	StartTime    time.Time
	MessagesSend atomic.Int32
}
type mockCollector struct{}
type mockDataProvider struct{}

func (m mockDataProvider) GetData() any {
	return struct{}{}
}

func (c mockCollector) Collect(result any) {}
func (c mockCollector) Close()             {}

func (m *mockClient) CallEndpoint(ctx context.Context, req any) any {
	log.Printf("Time Since start: %ds, old: %d, new: %d", int(time.Since(m.StartTime).Seconds()), m.MessagesSend.Load(), m.MessagesSend.Add(1))
	return struct{}{}
}

func TestPhase_CalculateRPS(t *testing.T) {
	p := Phase{
		Type:      2,
		Duration:  10 * time.Second,
		StartRPS:  0,
		Step:      1,
		startTime: time.Now().Add(-10 * time.Second),
	}

	n := p.CalculateRPS()

	if n != 10 {
		t.Errorf("Expected: 10, Got: %d", n)
	}

}
