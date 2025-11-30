package message

import (
	"strconv"
	"time"
)

type Response struct {
	Timestamp   time.Time
	Err         error
	Latency     time.Duration
	MessageSize int //in bytes
}

func (r Response) CSVHeaders() []string {
	return []string{"timestamp", "errors", "latency", "message-size"}
}

func (r Response) CSVRecord() []string {
	return []string{r.Timestamp.String(), r.Err.Error(), r.Latency.String(), strconv.Itoa(r.MessageSize)}
}
