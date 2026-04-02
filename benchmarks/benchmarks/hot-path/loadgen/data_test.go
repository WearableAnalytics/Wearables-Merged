package main

import (
	"encoding/json"
	"log"
	"sync/atomic"
	"testing"
)

func BenchmarkProvider_CreateBenchmarkMessage(b *testing.B) {
	p := Provider{
		MessageCount:    atomic.Int32{},
		MessageSize:     10240,
		TimestampLayout: "2006-01-02T15:04:05.000",
	}

	for i := 0; i < b.N; i++ {
		p.CreateBenchmarkMessage()
	}
}

func TestProvider_CreateBenchmarkMessage(t *testing.T) {
	p := Provider{
		MessageCount:    atomic.Int32{},
		MessageSize:     10240,
		TimestampLayout: "2006-01-02T15:04:05.000",
	}

	m := p.CreateBenchmarkMessage()

	bytes, err := json.Marshal(m)
	if err != nil {
		t.Error(err)
	}

	log.Printf("%dKB", len(bytes)/1024)

	log.Println(len(m.Measurements.Instantaneous))
}
