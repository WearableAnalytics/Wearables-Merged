package wplug

import (
	"io"
	"time"
)

type Request struct {
	Message []byte // This is an encoded JSON
}

type Response struct {
	Err     error
	Latency time.Duration
	Message io.Reader
}

func (r Response) CSVHeaders() []string {
	return []string{"Latency", "Error"}
}

func (r Response) CSVRecord() []string {
	return []string{r.Latency.String(), r.Err.Error()}
}

// TODO: implement Collector correctly

type Collector struct {
}

func NewCollector() *Collector {
	return nil
}

func (c Collector) Collect(result Response) {
	//TODO implement me
	panic("implement me")
}

func (c Collector) Close() {
	//TODO implement me
	panic("implement me")
}
