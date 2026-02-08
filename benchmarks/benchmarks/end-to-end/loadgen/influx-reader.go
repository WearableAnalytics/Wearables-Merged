package main

import (
	"context"
	"fmt"
	"log"
	"time"

	"github.com/influxdata/influxdb-client-go/v2"
)

type InfluxObserver struct {
	Config *InfluxObserverConfig
	Client influxdb2.Client
}

type InfluxObserverConfig struct {
	Addr   string
	Token  string
	Org    string
	Bucket string

	WindowSize time.Duration
	T0         time.Time
}

func NewInfluxObserver(conf *InfluxObserverConfig) *InfluxObserver {
	var observer InfluxObserver
	observer.Config = conf

	observer.Client = influxdb2.NewClient(conf.Addr, conf.Token)

	return &observer
}

func (obs *InfluxObserver) ObserveAndLog(ctx context.Context) error {
	queryAPI := obs.Client.QueryAPI(obs.Config.Org)
	ticker := time.NewTicker(obs.Config.WindowSize)
	defer ticker.Stop()

	lastObservedProducerTimestamp := obs.Config.T0

	log.Printf("message-id,t_produced,t_observed")
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			query := fmt.Sprintf(`
from(bucket: "%s")
  |> range(start: %s) 
  |> sort(columns: ["_time"])`, obs.Config.Bucket, lastObservedProducerTimestamp.Format(time.RFC3339Nano))

			result, err := queryAPI.Query(ctx, query)
			if err != nil {
				return err
			}

			for result.Next() {
				log.Printf(result.Record().String())
			}
		}
	}
}
