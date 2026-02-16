package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"
	"time"
)

type Client struct {
	ServiceUrl string
	AuthToken  string
	Client     *http.Client
}

func NewClient(serviceUrl, token string) *Client {
	return &Client{
		ServiceUrl: serviceUrl,
		Client:     &http.Client{},
		AuthToken:  token,
	}
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

	request, err := http.NewRequest("POST", c.ServiceUrl, bytes.NewBuffer(body))
	if err != nil {
		return Result{}
	}

	request.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.AuthToken))
	request.Header.Set("Content-Type", "application/json")

	sendTimestamp := time.Now()
	resp, err := c.Client.Do(request)
	if err != nil {
		log.Printf("not able to send request to service: %v", err)
		return Result{
			MessageID: messageId,
		}
	}

	if resp.StatusCode != http.StatusOK {
		log.Printf("Status-Code: %d, Status: %v", resp.StatusCode, resp.Status)
		return Result{
			MessageID:  messageId,
			StatusCode: resp.StatusCode,
		}
	}

	receivedTimestamp := time.Now()

	res := Result{
		MessageID:         messageId,
		StatusCode:        resp.StatusCode,
		SendTimestamp:     strconv.FormatInt(sendTimestamp.UnixNano(), 10),
		ReceivedTimestamp: strconv.FormatInt(receivedTimestamp.UnixNano(), 10),
	}

	return res
}
