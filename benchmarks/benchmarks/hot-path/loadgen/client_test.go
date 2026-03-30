package main

import (
	"testing"
	"time"
)

func TestPhase_CalculateRPS(t *testing.T) {
	rampUpDur := 10
	rPs := 50
	phase := Phase{
		Type:      1,
		StartTime: time.Now().Add(-10 * time.Second),
		Duration:  10 * time.Second,
		StartRPS:  0,
		Step:      rPs / rampUpDur,
	}

	expected := 50
	currRps := phase.CalculateRPS()
	if currRps != expected {
		t.Errorf("Expected: %d, Got: %d", expected, currRps)
	}
}
