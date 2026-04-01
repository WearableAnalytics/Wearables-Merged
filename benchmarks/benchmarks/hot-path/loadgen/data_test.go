package main

import (
	"sync/atomic"
	"testing"
)

func BenchmarkProvider_CreateBenchmarkMessage(b *testing.B) {
	p := Provider{
		MessageCount:    atomic.Int32{},
		MessageSize:     100240,
		TimestampLayout: "2006-01-02T15:04:05.000",
	}

	for i := 0; i < b.N; i++ {
		p.CreateBenchmarkMessage()
	}
}
