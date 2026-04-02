package main

import (
	"log"
	"testing"
	"time"
)

func TestProducer_GenerateNewLineProtocol(t *testing.T) {
	p := &Producer{
		PayloadConfig: PayloadConfig{
			MeasurementName: "test",
			Category:        "test",
			DeviceID:        "bench",
			Value:           42,
		},
	}

	for i := 0; i < 10; i++ {
		lp := p.GenerateNewLineProtocol()
		log.Println(lp)
	}
}

func TestPhase_CalculateRps(t *testing.T) {
	phase := Phase{
		Type:      1,
		startTime: time.Now().Add(-10 * time.Second),
		Duration:  10 * time.Second,
		StartRPS:  0,
		Step:      1,
	}

	expected := 10
	currRps := phase.CalculateRps()
	if currRps != expected {
		t.Errorf("Expected: %d, Got: %d", expected, currRps)
	}
}
