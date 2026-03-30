package main

import (
	"log"
	"testing"
)

func TestProducer_CalculateDeviceID(t *testing.T) {
	p := &Producer{}
	for i := 0; i < 10; i++ {
		for j := 0; j < i; j++ {
			log.Println(p.CalculateDeviceID())
		}
	}

	log.Println(p.MessageCounter.Load())
}
