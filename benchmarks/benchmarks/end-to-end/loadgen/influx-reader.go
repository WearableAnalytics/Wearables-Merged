package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/influxdata/influxdb-client-go/v2"
)

type InfluxObserver struct {
	Config  *InfluxObserverConfig
	Client  influxdb2.Client
	tracker *Tracker
}

type InfluxObserverConfig struct {
	Addr   string
	Token  string
	Org    string
	Bucket string

	WindowSize time.Duration
	T0         time.Time
}

func NewInfluxObserver(conf *InfluxObserverConfig, tracker *Tracker) *InfluxObserver {
	var observer InfluxObserver
	observer.Config = conf

	observer.Client = influxdb2.NewClient(conf.Addr, conf.Token)
	observer.tracker = tracker

	return &observer
}

func (obs *InfluxObserver) ObserveBenchmark(ctx context.Context, duration time.Duration) {
	queryApi := obs.Client.QueryAPI(obs.Config.Org)
	query := fmt.Sprintf(`
from(bucket: "%s")
  |> range(start: -%ds)
  |> filter(fn: (r) => r._measurement == "heart-rate")
  |> pivot(rowKey: ["_time", "device-id"], columnKey: ["_field"], valueColumn: "_value")`,
		obs.Config.Bucket,
		int(duration),
	)

	res, err := queryApi.Query(ctx, query)
	if err != nil {
		log.Printf("error occurred when executing query: %v", err)
		return
	}

	for res.Next() {
		rec := res.Record()
		values := rec.Values()

		var value int64
		v, ok := values["value"]
		if !ok {
			log.Printf("ERROR: missing field 'value'")
			continue
		}

		switch val := v.(type) {
		case float64:
			value = int64(val)
		case int64:
			value = val
		default:
			log.Printf("ERROR: unexpected type for 'value': %T (%v)", v, v)
			continue
		}

		var tIngested time.Time
		t, ok := values["t_ingested"]
		if !ok {
			log.Printf("ERROR: missing field 't_ingested'")
			continue
		}

		switch ts := t.(type) {
		case int64:
			tIngested = time.Unix(0, ts)
		case time.Time:
			tIngested = ts
		default:
			log.Printf("ERROR: unexpected type for 't_ingested': %T (%v)", t, t)
			continue
		}

		if !obs.tracker.AddIngestTime(value, tIngested) {
			log.Printf("ERROR: AddIngestTime failed for value=%d, t_ingested=%v", value, tIngested)
		}
	}

	if err = res.Err(); err != nil {
		log.Printf("ERROR: result iteration failed: %v", err)
	}

	obs.tracker.PrintAsCsv()
}
