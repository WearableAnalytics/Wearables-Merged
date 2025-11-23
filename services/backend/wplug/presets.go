package wplug

import (
	"time"

	lg "github.com/luccadibe/go-loadgen"
)

type Preset interface {
	GenerateConfig() lg.Config
}

type PresetTypes interface {
	Smoke | Avg | Stress | Spike | Breakpoint | Soak
}

type Smoke struct {
	Phases    []lg.TestPhase
	Duration  time.Duration
	Client    lg.Client[Request, Response]
	Supplier  Supplier
	Collector Collector
}

func NewSmoke(client lg.Client[Request, Response], supplier Supplier, collector Collector) (Smoke, error) {
	var smoke Smoke

	test := lg.TestPhase{
		Name:      "increment",
		Type:      "constant",
		StartTime: 0,
		Duration:  3 * time.Minute,
		StartRPS:  20,
		EndRPS:    20,
		Step:      1,
	}

	smoke.Phases = append(smoke.Phases, test)
	smoke.Duration = 3 * time.Minute
	smoke.Client = client
	smoke.Supplier = supplier
	smoke.Collector = collector

	return smoke, nil
}

func (s Smoke) GenerateConfig() *lg.Config {
	return &lg.Config{
		GenerateWorkload: false,
		MaxDuration:      s.Duration,
		Phases:           s.Phases,
	}
}

type Avg struct{}

type Stress struct{}

type Spike struct{}

type Breakpoint struct{}

type Soak struct{}
