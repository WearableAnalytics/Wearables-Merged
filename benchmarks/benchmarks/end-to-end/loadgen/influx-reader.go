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

type Record struct {
	tProduced time.Time
	tObserved time.Time
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

func (obs *InfluxObserver) ObserveAndLog(ctx context.Context) {
	queryAPI := obs.Client.QueryAPI(obs.Config.Org)
	ticker := time.NewTicker(obs.Config.WindowSize)
	defer ticker.Stop()

	lastObserved := obs.Config.T0
	observeMap := make(map[string]Record)

	for {
		select {
		case <-ctx.Done():
			for msgID, rec := range observeMap {
				log.Printf("%s,%d,%d",
					msgID,
					rec.tProduced.UnixMilli(),
					rec.tObserved.UnixMilli(),
				)
			}
			return

		case <-ticker.C:
			query := fmt.Sprintf(`
from(bucket: "%s")
  |> range(start: time(v: "%s"))
  |> filter(fn: (r) => r._measurement == "heart-rate")`,
				obs.Config.Bucket,
				lastObserved.Format(time.RFC3339Nano),
			)

			res, err := queryAPI.Query(ctx, query)
			if err != nil {
				continue
			}

			maxTime := lastObserved
			tObserved := time.Now()

			for res.Next() {
				rec := res.Record()
				tProduced := rec.Time()

				messageId := fmt.Sprintf("%s-%.0f",
					rec.ValueByKey("device-id-reference"),
					rec.Value(),
				)

				observeMap[messageId] = Record{
					tProduced: tProduced,
					tObserved: tObserved,
				}

				if tProduced.After(maxTime) {
					maxTime = tProduced
				}
			}

			res.Close()
			lastObserved = maxTime
		}
	}
}
