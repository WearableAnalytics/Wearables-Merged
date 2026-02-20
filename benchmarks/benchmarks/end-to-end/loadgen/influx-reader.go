package main

import (
	"context"
	"fmt"
	"hash/fnv"
	"log"
	"time"

	"github.com/influxdata/influxdb-client-go/v2"
)

type InfluxObserver struct {
	Config *InfluxObserverConfig
	Client influxdb2.Client
}

type Record struct {
	tProduced    time.Time
	tObserved    time.Time
	LineProtocol string
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
	observeMap := make(map[uint64]Record)

	hash := fnv.New64a()

	for {
		select {
		case <-ctx.Done():
			log.Printf("hash,t_produced,t_observed,line-protocol")
			for msgID, rec := range observeMap {
				log.Printf("%d,%d,%d,%s",
					msgID,
					rec.tProduced.UnixMilli(),
					rec.tObserved.UnixMilli(),
					rec.LineProtocol,
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

			hash.Reset()

			res, err := queryAPI.Query(ctx, query)
			if err != nil {
				continue
			}

			maxTime := lastObserved
			tObserved := time.Now()

			for res.Next() {
				rec := res.Record()
				tProduced := rec.Time()

				_, err := hash.Write([]byte(rec.String()))
				if err != nil {
					continue
				}

				key := hash.Sum64()

				observeMap[key] = Record{
					tProduced:    tProduced,
					tObserved:    tObserved,
					LineProtocol: rec.String(),
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
