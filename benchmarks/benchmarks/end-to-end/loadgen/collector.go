package main

import (
	"log"
	"time"
)

type Result struct {
	Records   []InstantMeasurement
	tResponse time.Time
	Error     string
}

type Collector struct {
	tracker *Tracker
}

func (c Collector) Collect(res Result) {
	for _, r := range res.Records {
		id := int64(r.Value)

		tProduced, err := time.Parse("2006-01-02T15:04:05.000", r.Timestamp)
		if err != nil {
			log.Fatalf("not able to parse timestamp")
		}

		rec := Record{
			Identifier: id,
			tProduced:  tProduced,
			tResponse:  res.tResponse,
			Error:      res.Error,
		}

		c.tracker.RegisterRecord(rec)
	}
}

func (c Collector) Close() {}
