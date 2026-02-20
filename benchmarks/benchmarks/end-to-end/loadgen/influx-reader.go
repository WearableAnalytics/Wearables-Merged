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
	log.Println("starting to execute observer")
	queryApi := obs.Client.QueryAPI(obs.Config.Org)

	query := fmt.Sprintf(`
from(bucket: "%s")
  |> range(start: "-2m")
  |> filter(fn: (r) => r._measurement == "heart-rate")`,
		obs.Config.Bucket,
		//obs.Config.T0.Format(time.RFC3339Nano),
	)

	log.Println("now executing query: ", query)

	res, err := queryApi.Query(ctx, query)
	if err != nil {
		log.Fatalf("error occurred when executing query: %v", err)
	}

	for res.Next() {
		rec := res.Record()

		tIngestedNs := rec.ValueByKey("t_ingested").(int64)
		tIngestedTime := time.Unix(0, tIngestedNs)

		value := rec.ValueByKey("value").(float64)

		log.Printf("%v, %v, %v", rec.Values(), tIngestedTime, value)
	}
}
