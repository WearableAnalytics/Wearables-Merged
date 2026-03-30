package main

import (
	"context"
	"testing"
	"time"
)

func TestPhase_RunPhase(t *testing.T) {
	p := Phase{
		Type:     1,
		Duration: 10 * time.Second,
		StartRPS: 0,
		Step:     1,
	}

	p.RunPhase(context.Background())
}
