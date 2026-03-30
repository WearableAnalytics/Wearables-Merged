package main

import "time"

type Producer struct {
}

var (
	Constant = 1
	RampUp   = 2
	RampDown = 3
)

type Phase struct {
	Type      int
	Duration  time.Duration
	StartRPS  int
	Step      int
	startTime time.Time
}

func (p *Phase) CalculateRPS() int {
	var rps int
	if p.Type == Constant {
		rps = p.StartRPS
	} else if p.Type == RampUp {
		rps = int(time.Since(p.startTime).Seconds())*p.Step + p.StartRPS
	} else if p.Type == RampDown {
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
