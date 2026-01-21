package main

import (
	"bytes"
	"context"
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"time"
)

type Client struct {
	ServiceUrl string
}

func NewClient(serviceUrl string) *Client {
	return &Client{ServiceUrl: serviceUrl}
}

func (c Client) CallEndpoint(ctx context.Context, req Payload) Result {
	select {
	case <-ctx.Done():
		return Result{}
	default:
	}

	messageId := req.DeviceInfo.DeviceId

	body, err := json.Marshal(req)
	if err != nil {
		log.Printf("not able to parse request-payload, aborting benchmark")
		return Result{
			MessageID: messageId,
		}
	}

	sendTimestamp := time.Now()
	resp, err := http.Post(c.ServiceUrl, "application/json", bytes.NewBuffer(body))
	if err != nil {
		log.Printf("not able to send request to service: %v", err)
		return Result{
			MessageID: messageId,
		}
	}

	if resp.StatusCode != http.StatusOK {
		log.Printf("Status-Code: %d, Status: %v", resp.StatusCode, resp.Status)
		return Result{
			MessageID: messageId,
		}
	}

	receivedTimestamp := time.Now()

	res := Result{
		MessageID:         messageId,
		SendTimestamp:     strconv.FormatInt(sendTimestamp.UnixNano(), 10),
		ReceivedTimestamp: strconv.FormatInt(receivedTimestamp.UnixNano(), 10),
	}

	return res
}
