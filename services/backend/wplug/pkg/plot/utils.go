package plot

import (
	"fmt"
	"sort"
	"strings"
	"time"

	"gonum.org/v1/plot/plotter"
)

type Number interface {
	int | int64 | float32 | float64
}

func MapToXY[T Number](start time.Time, m map[time.Time]T) plotter.XYs {
	// Extract and sort timestamps
	var keys []time.Time
	for ts := range m {
		keys = append(keys, ts)
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i].Before(keys[j]) })

	pts := make(plotter.XYs, len(keys))
	for i, ts := range keys {
		pts[i].X = ts.Sub(start).Seconds()
		pts[i].Y = float64(m[ts])
	}

	return pts
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

func percentile(values []float64, p float64) float64 {
	if len(values) == 0 {
		return 0
	}

	cp := append([]float64(nil), values...)
	sort.Float64s(cp)

	index := int(float64(len(cp)-1) * p)
	return cp[index]
}

func parseDurationToMS(s string) (float64, error) {
	d, err := time.ParseDuration(s)
	if err != nil {
		return 0, err
	}
	return float64(d) / float64(time.Microsecond), nil
}

func stripMonotonic(t string) string {
	if idx := strings.Index(t, " m="); idx != -1 {
		return t[:idx]
	}
	return t
}
