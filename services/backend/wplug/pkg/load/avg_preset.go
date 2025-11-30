package load

import (
	"fmt"
	"time"
	"wplug/pkg/message"

	"github.com/google/uuid"
	go_loadgen "github.com/luccadibe/go-loadgen"
)

func NewAverageLoad(
	client go_loadgen.Client[message.Message, message.Response],
	provider message.Provider,
	collector *go_loadgen.CSVCollector[message.Response],
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
