package main

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	"github.com/influxdata/influxdb-client-go/v2"
)

type Observer struct {
	InfluxClient influxdb2.Client
	Records      map[string]Record
	mu           sync.Mutex

	InfluxAddr   string
	InfluxToken  string
	InfluxOrg    string
	InfluxBucket string

	StartTime time.Time
}

type Record struct {
	MessageId    string
	TimeProduced time.Time
	TimeObserved time.Time
}

func NewObserver(addr, token, org, bucket string, startTime time.Time) *Observer {
	influxClient := influxdb2.NewClient(addr, token)

	return &Observer{
		InfluxClient: influxClient,
		Records:      make(map[string]Record),
		InfluxAddr:   addr,
		InfluxToken:  token,
		InfluxOrg:    org,
		InfluxBucket: bucket,
		StartTime:    startTime,
	}
}

func (o *Observer) Run(ctx context.Context) {
	api := o.InfluxClient.QueryAPI(o.InfluxOrg)

	query := fmt.Sprintf(`
	from(bucket: "%s")
	  |> range(start: -%ds)
	  |> filter(fn: (r) => r._measurement == "ml_predictions")
	  |> pivot(rowKey: ["_time", "device_id"], columnKey: ["_field"], valueColumn: "_value")`,
		o.InfluxBucket,
		int(time.Since(o.StartTime).Seconds()+time.Minute.Seconds()),
	)

	log.Printf("executing query: %s", query)
	res, err := api.Query(ctx, query)
	if err != nil {
		log.Printf("error occurred when executing query: %v", err)
	}

	for res.Next() {
		rec := res.Record()
		values := rec.Values()

		var messageId string
		m, ok := values["device_id"]
		if !ok {
			log.Printf("ERROR: missing field 'device_id'")
			continue
		}

		switch msg := m.(type) {
		case string:
			messageId = msg
		default:
			log.Printf("ERROR: unexpected type for 'device-id': %T (%v)", m, m)
			continue
		}

		var timeObserved time.Time
		t, ok := values["created_at"]
		if !ok {
			log.Printf("ERROR: missing field 'created_at'")
			continue
		}

		switch tO := t.(type) {
		case int64:
			timeObserved = time.Unix(0, tO)
		case time.Time:
			timeObserved = tO
		case string:
			parsed, err := time.Parse("2006-01-02 15:04:05.999999Z07:00", tO)
			if err != nil {
				log.Printf("ERROR: failed to parse 'created_at' string: %v", err)
				continue
			}
			timeObserved = parsed
		default:
			log.Printf("ERROR: unexpected type for 'created_at': %T (%v)", m, m)
			continue
		}

		timeProduced := rec.Time().UTC()

		record := Record{
			MessageId:    messageId,
			TimeProduced: timeProduced,
			TimeObserved: timeObserved,
		}

		o.mu.Lock()
		o.Records[messageId] = record
		o.mu.Unlock()

	}

	o.PrintAsCsv()
}

func (o *Observer) PrintAsCsv() {
	log.Printf("message-id,t-produced,t-observed")

	o.mu.Lock()
	defer o.mu.Unlock()

	for _, rec := range o.Records {
		log.Printf("%s,%d,%d", rec.MessageId, rec.TimeProduced.UnixMilli(), rec.TimeObserved.UnixMilli())
	}
}
