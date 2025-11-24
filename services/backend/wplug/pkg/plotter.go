package pkg

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
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
	err := p.GenerateBytesPlot(path.Join(p.OutputFolder, "bytes.svg"))
	if err != nil {
		return err
	}
	return nil
}

func (p Plotter) GenerateBytesPlot(outputPath string) error {
	data, err := p.PlotBytesPerSecond()
	if err != nil {
		return err
	}

	var start time.Time
	for ts := range data {
		if start.IsZero() || ts.Before(start) {
			start = ts
		}
	}

	pts := MapToXY(start, data)

	return PlotLineToSVG(pts, outputPath, "Bytes/sec", "Time (s)", "Bytes/sec")
}

func (p Plotter) PlotBytesPerSecond() (map[time.Time]int64, error) {
	file, err := os.Open(p.InputPath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	reader.FieldsPerRecord = -1

	if _, err := reader.Read(); err != nil {
		return nil, err
	}

	bytesPerSecond := make(map[time.Time]int64)

	for {

		record, err := reader.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("error reading CSV: %w", err)
		}

		rawTs := stripMonotonic(record[0])

		ts, err := parseTimestamp(rawTs)
		if err != nil {
			return nil, err
		}

		ts = ts.Truncate(time.Second)

		bytesVal, err := strconv.ParseInt(record[3], 10, 64)
		if err != nil {
			return nil, fmt.Errorf("failed to parse bytes '%s': %w", record[3], err)
		}

		bytesPerSecond[ts] += bytesVal
	}

	return bytesPerSecond, err
}

func MapToXY(start time.Time, m map[time.Time]int64) plotter.XYs {
	// Extract and sort timestamps
	var keys []time.Time
	for ts := range m {
		keys = append(keys, ts)
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i].Before(keys[j]) })

	pts := make(plotter.XYs, len(keys))
	for i, ts := range keys {
		pts[i].X = ts.Sub(start).Seconds() // relative X
		pts[i].Y = float64(m[ts])          // bytes/sec
	}

	return pts
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

func parseTimestamp(raw string) (time.Time, error) {
	raw = stripMonotonic(raw)

	layouts := []string{
		"2006-01-02 15:04:05.999999999 -0700 MST",
		"2006-01-02 15:04:05.999999999",
	}

	for _, layout := range layouts {
		ts, err := time.Parse(layout, raw)
		if err == nil {
			return ts, nil
		}
	}

	return time.Time{}, fmt.Errorf("failed to parse timestamp '%s'", raw)
}

func stripMonotonic(t string) string {
	if idx := strings.Index(t, " m="); idx != -1 {
		return t[:idx]
	}
	return t
}
