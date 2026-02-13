package main

import (
	"fmt"
	"log"
	"strconv"
	"testing"
)

func BenchmarkProvider_GetData(b *testing.B) {
	sizes := []int{1024, 10240, 51200, 102400}

	for _, size := range sizes {
		provider := NewProvider(size)
		b.Run(fmt.Sprintf("size_%d", size), func(b *testing.B) {
			b.ReportAllocs()

			for i := 0; i < b.N; i++ {
				_ = provider.GetData()
			}
		})
	}
}

func TestProvider_GetData(t *testing.T) {
	provider := NewProvider(1024)

	data1 := provider.GetData()
	data2 := provider.GetData()

	id1, err := strconv.Atoi(data1.DeviceInfo.DeviceId)
	if err != nil {
		t.Fail()
	}
	id2, err := strconv.Atoi(data2.DeviceInfo.DeviceId)
	if err != nil {
		t.Fail()
	}

	if id1 > id2 {
		log.Printf("id1: %d, id2: %d", id1, id2)
		t.Fail()
	}

	log.Printf("id1: %d, id2: %d", id1, id2)

	if len(data1.Measurements.Instantaneous) != len(data2.Measurements.Instantaneous) {
		log.Printf("data1 len: %d, last counter: %.2f", len(data1.Measurements.Instantaneous),
			data1.Measurements.Instantaneous[len(data1.Measurements.Instantaneous)-1].Value)
		log.Printf("data2 len: %d, last counter: %.2f", len(data2.Measurements.Instantaneous),
			data2.Measurements.Instantaneous[len(data2.Measurements.Instantaneous)-1].Value)
		t.Fail()
	}

	log.Printf("data1 len: %d, last counter: %.2f", len(data1.Measurements.Instantaneous),
		data1.Measurements.Instantaneous[len(data1.Measurements.Instantaneous)-1].Value)
	log.Printf("data2 len: %d, last counter: %.2f", len(data2.Measurements.Instantaneous),
		data2.Measurements.Instantaneous[len(data2.Measurements.Instantaneous)-1].Value)
}
