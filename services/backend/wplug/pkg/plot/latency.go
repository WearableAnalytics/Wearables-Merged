package plot

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"time"

	"gonum.org/v1/plot/plotter"
)

// [X] MedianLatency
// [X] 99th Percentile Latency
// BoxPlot (combines both)
// BoxPlot for Requests/sec

func (p Plotter) GetLatencies() (map[time.Time][]float64, error) {
	file, err := os.Open(p.InputPath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	reader.FieldsPerRecord = -1

	headers, err := reader.Read()
	if err != nil {
		return nil, err
	}

	latenciesPerSecond := make(map[time.Time][]float64)
	//requestsPerSecond := make(map[time.Time]int64)

	timestampHeader := "timestamp"
	latencyHeader := "latency"

	recordMap := make(map[string]int, len(headers))
	for i, header := range headers {
		if _, exists := recordMap[header]; exists {
			return nil, fmt.Errorf("duplicate header found: %s", header)
		}
		recordMap[header] = i
	}

	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}

		rawTs := stripMonotonic(record[recordMap[timestampHeader]])
		ts, err := parseTimestamp(rawTs)
		if err != nil {
			return nil, err
		}
		ts = ts.Truncate(time.Second)

		rawDur, err := parseDurationToMS(record[recordMap[latencyHeader]])
		if err != nil {
			return nil, err
		}

		latenciesPerSecond[ts] = append(latenciesPerSecond[ts], rawDur)
		// requestsPerSecond[ts]++
	}

	return latenciesPerSecond, nil
}

func (p Plotter) MedianLatency() (plotter.XYs, error) {

	latenciesPerSecond, err := p.GetLatencies()
	if err != nil {
		return nil, err
	}

	xys := make(map[time.Time]float64, len(latenciesPerSecond))
	for t, vals := range latenciesPerSecond {
		if len(vals) == 0 {
			continue
		}
		median := percentile(vals, 0.5)
		xys[t] = median
	}
	var start time.Time
	for ts := range latenciesPerSecond {
		if start.IsZero() || ts.Before(start) {
			start = ts
		}
	}

	return MapToXY[float64](start, xys), err
}

func (p Plotter) P99Latency() (plotter.XYs, error) {
	latenciesPerSecond, err := p.GetLatencies()
	if err != nil {
		return nil, err
	}

	xys := make(map[time.Time]float64, len(latenciesPerSecond))
	for t, vals := range latenciesPerSecond {
		if len(vals) == 0 {
			continue
		}
		p99 := percentile(vals, 0.99)
		xys[t] = p99
	}
	var start time.Time
	for ts := range latenciesPerSecond {
		if start.IsZero() || ts.Before(start) {
			start = ts
		}
	}

	return MapToXY[float64](start, xys), err
}
