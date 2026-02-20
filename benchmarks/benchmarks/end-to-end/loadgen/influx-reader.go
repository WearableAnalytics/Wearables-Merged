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

func (obs *InfluxObserver) ObserveBenchmark(ctx context.Context) {
	queryApi := obs.Client.QueryAPI(obs.Config.Org)

	query := fmt.Sprintf(`
from(bucket: "%s")
  |> range(start: -3m)
  |> filter(fn: (r) => r._measurement == "heart-rate")
  |> pivot(rowKey: ["_time", "device-id"], columnKey: ["_field"], valueColumn: "_value")`,
		obs.Config.Bucket,
		//obs.Config.T0.Format(time.RFC3339Nano),
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
		if v, ok := values["value"]; ok {
			if i, ok := v.(float64); ok {
				value = int64(i)
			}
		}

		var tIngested time.Time
		if t, ok := values["t_ingested"]; ok {
			if i, ok := t.(int64); ok {
				tIngested = time.Unix(0, i)
			}
		}

		obs.tracker.AddIngestTime(value, tIngested)
	}

	obs.tracker.PrintAsCsv()
}
