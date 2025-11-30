package load

import (
	"fmt"
	"time"
	"wplug/pkg/message"

	go_loadgen "github.com/luccadibe/go-loadgen"
)

type Preset interface {
	GenerateConfig() go_loadgen.Config
	GenerateWorkload() error
}

type Workload struct {
	Name      string
	Duration  time.Duration
	Phases    []go_loadgen.TestPhase
	Client    go_loadgen.Client[message.Message, message.Response]
	Provider  message.Provider
	Collector *go_loadgen.CSVCollector[message.Response]
}

func (s Workload) generateConfig() *go_loadgen.Config {
	return &go_loadgen.Config{
		GenerateWorkload: false,
		MaxDuration:      s.Duration,
		Phases:           s.Phases,
	}
}

func (s Workload) GenerateWorkload() error {
	startTime := time.Now()
	runner, err := go_loadgen.NewEndpointWorkload(s.Name, s.generateConfig(), s.Client, s.Provider, s.Collector)
	if err != nil {
		return err
	}

	fmt.Printf("starting runner: %s with config: \nDuration:%v\nMaxSize:%d\nVU:%d", s.Name, s.Duration, s.Provider.MaxSize, s.Provider.DeviceCount)
	runner.Run()
	fmt.Printf("finished running in: %v", time.Since(startTime))

	return nil
}
