package main

import (
	"fmt"
	"sync/atomic"
	"testing"
)

func TestProducer_CalculateDeviceID(t *testing.T) {
	p := Producer{
		MessageCounter: atomic.Int64{},
		KafkaConfig:    KafkaConfig{},
		PayloadConfig: PayloadConfig{
			MeasurementName: "a",
			Category:        "b",
			BaseDeviceID:    "c",
			Value:           72,
			ClientIndex:     0,
			NumClients:      10,
		},
		LoadConfig: LoadConfig{
			RPS: 1000,
		},
	}

	for i := 0; i < 10000; i++ {
		fmt.Println(p.CalculateDeviceID())
	}
}
