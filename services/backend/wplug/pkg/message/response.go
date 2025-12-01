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
	errMsg := ""
	if r.Err != nil {
		errMsg = r.Err.Error()
	}

	return []string{
		r.Timestamp.String(),
		errMsg,
		r.Latency.String(),
		strconv.Itoa(r.MessageSize),
	}
}
