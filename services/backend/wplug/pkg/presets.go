package pkg

import (
	"fmt"
	"time"

	"github.com/google/uuid"
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
	Client    go_loadgen.Client[Message, Response]
	Provider  ExampleProvider
	Collector *go_loadgen.CSVCollector[Response]
}

func NewSmoke(
	client go_loadgen.Client[Message, Response],
	provider ExampleProvider,
	collector *go_loadgen.CSVCollector[Response],
) *Workload {

	var smoke Workload
	testId := uuid.New().ID()
	smoke.Name = fmt.Sprintf("Workload-Test-%d", testId)
	smoke.Duration = 3 * time.Minute

	phase := go_loadgen.TestPhase{
		Name:      "increment",
		Type:      "constant",
		StartTime: 0,
		Duration:  smoke.Duration,
		StartRPS:  1,
		EndRPS:    1,
		Step:      1,
	}

	smoke.Phases = append(smoke.Phases, phase)
	smoke.Client = client
	smoke.Provider = provider
	smoke.Collector = collector

	return &smoke
}

func NewAverageLoad(
	client go_loadgen.Client[Message, Response],
	provider ExampleProvider,
	collector *go_loadgen.CSVCollector[Response],
) *Workload {

	var average Workload
	testID := fmt.Sprintf("Avg-Test-%d", uuid.New().ID())
	average.Name = testID
	average.Duration = 40 * time.Minute

	rampUp := go_loadgen.TestPhase{
		Name:      "increment",
		Type:      "constant",
		StartTime: 0,
		Duration:  5 * time.Minute,
		StartRPS:  0,
		EndRPS:    200,
		Step:      1,
	}
	test := go_loadgen.TestPhase{
		Name:      "constant",
		Type:      "constant",
		StartTime: 5 * time.Minute,
		Duration:  30 * time.Minute,
		StartRPS:  200,
		EndRPS:    250,
		Step:      2,
	}
	rampDown := go_loadgen.TestPhase{
		Name:      "decrement",
		Type:      "constant",
		StartTime: 35 * time.Minute,
		Duration:  5 * time.Minute,
		StartRPS:  250,
		EndRPS:    0,
		Step:      3,
	}

	average.Phases = append(average.Phases, rampUp, test, rampDown)
	average.Client = client
	average.Provider = provider
	average.Collector = collector

	return &average
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
