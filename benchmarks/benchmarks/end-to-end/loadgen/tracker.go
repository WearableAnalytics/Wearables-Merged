package main

import (
	"log"
	"sync"
	"sync/atomic"
	"time"
)

type Tracker struct {
	Records        map[int64]Record
	MessageCounter atomic.Int64
	mu             sync.Mutex
}

type Record struct {
	Identifier int64     // unique message-counter (stored as value in Influx)
	tProduced  time.Time //from Ingestion-Service
	tResponse  time.Time //from Ingestion-Service
	tIngested  time.Time //from Influx
	Error      string
}

func NewTracker() *Tracker {
	return &Tracker{
		Records:        make(map[int64]Record),
		MessageCounter: atomic.Int64{},
		mu:             sync.Mutex{},
	}
}

func (t *Tracker) RegisterRecord(rec Record) bool {
	t.mu.Lock()
	defer t.mu.Unlock()

	id := rec.Identifier

	if _, ok := t.Records[id]; !ok {
		t.Records[id] = rec
		return true
	}

	// log.Printf("[client] record with id: %d exists", id)
	return false
}

func (t *Tracker) AddIngestTime(id int64, tIngested time.Time) bool {
	t.mu.Lock()
	defer t.mu.Unlock()

	if _, ok := t.Records[id]; ok {
		rec := t.Records[id]
		rec.tIngested = tIngested
		t.Records[id] = rec

		return true
	}

	log.Printf("[observer] record with id: %d does not exist", id)
	return false
}

func (t *Tracker) PrintAsCsv() {
	t.mu.Lock()
	defer t.mu.Unlock()

	log.Println("message-id,t_produced,t_response,t_ingested,error")
	for id, rec := range t.Records {

		var tIn int64 = 0

		if !rec.tIngested.IsZero() {
			tIn = rec.tIngested.UnixMilli()
		}

		log.Printf("%d,%d,%d,%d,%s",
			id,
			rec.tProduced.UnixMilli(),
			rec.tResponse.UnixMilli(),
			tIn,
			rec.Error,
		)
	}
}
