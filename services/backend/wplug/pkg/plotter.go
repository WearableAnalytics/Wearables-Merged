package pkg

import (
	"encoding/csv"
	"os"
	"time"
)

type Plotter struct {
	FilePath string
	Plots    []Plot
}

type Plot struct {
	Name string
	X    string
	Y    string
}

func (p Plotter) GeneratePlots() {

	// 1. Which Plots do I want to do
	// -> requests/sec (group by second and count)
	// -> errors/requests (breakpoint)
	// -> latency/requests (=> avg until 99 percentile)
	// -> bytes/sec (=> cumlative)

	//2025-11-24 10:32:53.615602 +0100 CET m=+14.105431585,,231.125µs,282
	//2025-11-24 10:32:53.615608 +0100 CET m=+14.105437085,,226.75µs,282
	//2025-11-24 10:32:53.615615 +0100 CET m=+14.105444585,,225.666µs,282

}

func (p Plotter) PlotRequestsPerSecond() map[time.Time]int {
	return nil
}

func computeRequestsPerSecond(filePath string) ([]float64, []float64, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, nil, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	reader.FieldsPerRecord = -1

	// remove the header
	if _, err := reader.Read(); err != nil {
		return nil, nil, err
	}
	return nil, nil, nil
}

func (p Plotter) PlotAvgLatencyPerSecond() map[time.Time]int {
	return nil
}

func (p Plotter) PlotBytesPerSecond() map[time.Time]int64 {
	return nil
}
