package load

import (
	"fmt"
	"time"
	"wplug/pkg/message"

	"github.com/google/uuid"
	go_loadgen "github.com/luccadibe/go-loadgen"
)

func NewSmoke(
	client go_loadgen.Client[message.Message, message.Response],
	provider message.Provider,
	collector *go_loadgen.CSVCollector[message.Response],
) *Workload {

	var smoke Workload
	testId := uuid.New().ID()
	smoke.Name = fmt.Sprintf("Workload-Test-%d", testId)
	smoke.Duration = 2 * time.Minute

	phase := go_loadgen.TestPhase{
		Name:      "increment",
		Type:      "variable",
		StartTime: 0,
		Duration:  smoke.Duration,
		StartRPS:  1,
		EndRPS:    200,
		Step:      1,
	}

	smoke.Phases = append(smoke.Phases, phase)
	smoke.Client = client
	smoke.Provider = provider
	smoke.Collector = collector

	return &smoke
}
