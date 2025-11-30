package plot

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"time"

	"gonum.org/v1/plot"
	"gonum.org/v1/plot/plotter"
	"gonum.org/v1/plot/vg"
)

type Plotter struct {
	InputPath    string
	OutputFolder string
}

func (p Plotter) GeneratePlots() error {
	xys, err := p.ReadAllCSVForPlot()
	if err != nil {
		return err
	}

	err = PlotLineToSVG(xys[0], path.Join(p.OutputFolder, "bytes.svg"), "Bytes/sec", "Time (s)", "Bytes/sec")
	if err != nil {
		return err
	}

	err = PlotLineToSVG(xys[1], path.Join(p.OutputFolder, "requests.svg"), "Requests/sec", "Time (s)", "Requests/sec")
	if err != nil {
		return err
	}

	// Avg Latency Plot
	err = PlotLineToSVG(xys[2], path.Join(p.OutputFolder, "latency.svg"), "Avg-Latency/ms", "Time (ms)", "Average Latency")
	if err != nil {
		return err
	}

	return nil
}

func (p Plotter) ReadAllCSVForPlot() ([]plotter.XYs, error) {
	file, err := os.Open(p.InputPath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	bytesPerSecond := make(map[time.Time]int64)
	requestsPerSecond := make(map[time.Time]int64)
	latenciesPerSecond := make(map[time.Time][]float64)

	reader := csv.NewReader(file)
	reader.FieldsPerRecord = -1

	headers, err := reader.Read()
	if err != nil {
		return nil, err
	}

	recordMap := make(map[string]int, len(headers))
	for i, header := range headers {
		if _, exists := recordMap[header]; exists {
			return nil, fmt.Errorf("duplicate header found: %s", header)
		}
		recordMap[header] = i
	}

	// column names
	timestampIndex := recordMap["timestamp"]
	bytesHeader := "message-size"
	latencyHeader := "latency"

	for {
		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}

		rawTs := stripMonotonic(record[timestampIndex])
		ts, err := parseTimestamp(rawTs)
		if err != nil {
			return nil, err
		}
		ts = ts.Truncate(time.Second)

		bytesVal, err := strconv.ParseInt(record[recordMap[bytesHeader]], 10, 64)
		if err != nil {
			return nil, err
		}
		bytesPerSecond[ts] += bytesVal

		rawDur, err := parseDurationToMS(record[recordMap[latencyHeader]])
		if err != nil {
			return nil, err
		}

		latenciesPerSecond[ts] = append(latenciesPerSecond[ts], rawDur)

		requestsPerSecond[ts]++
	}

	p99LatencyPerSecond := make(map[time.Time]float64)
	for ts, slice := range latenciesPerSecond {
		if len(slice) == 0 {
			p99LatencyPerSecond[ts] = 0
			continue
		}
		p99LatencyPerSecond[ts] = percentile(slice, 0.99)
	}

	bytesOut := make(map[time.Time]int64)
	reqOut := make(map[time.Time]int64)
	for ts, v := range bytesPerSecond {
		bytesOut[ts] = v
	}
	for ts, v := range requestsPerSecond {
		reqOut[ts] = v
	}

	var start time.Time
	for ts := range bytesOut {
		if start.IsZero() || ts.Before(start) {
			start = ts
		}
	}

	maps := make([]plotter.XYs, 3)
	maps[0] = MapToXY[int64](start, bytesOut)
	maps[1] = MapToXY[int64](start, reqOut)
	maps[2] = MapToXY[float64](start, p99LatencyPerSecond)

	return maps, nil

}

func PlotLineToSVG(points plotter.XYs, outputPath string, title string, X string, Y string) error {
	if filepath.Ext(outputPath) != ".svg" {
		return fmt.Errorf("output-path must be svg is: %s (ext: %s)", outputPath, filepath.Ext(outputPath))
	}
	p := plot.New()
	p.Title.Text = title
	p.X.Label.Text = X
	p.Y.Label.Text = Y

	line, err := plotter.NewLine(points)
	if err != nil {
		return err
	}
	p.Add(line)

	// Save 12×4 inch PNG
	return p.Save(12*vg.Inch, 4*vg.Inch, outputPath)
}
