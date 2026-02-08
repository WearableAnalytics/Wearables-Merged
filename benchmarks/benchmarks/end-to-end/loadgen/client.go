package main

import (
	"bytes"
	"context"
	"encoding/json"
	"log"
	"net/http"
)

type Client struct {
	ServerURL string
}

type Result struct{}

func NewClient(serverUrl string) *Client {
	return &Client{ServerURL: serverUrl}
}

func (c Client) CallEndpoint(ctx context.Context, req Payload) Result {
	select {
	case <-ctx.Done():
		return Result{}
	default:
	}

	body, err := json.Marshal(req)
	if err != nil {
		log.Fatalf("not able to marshall body: %v", err)
	}

	resp, err := http.Post(c.ServerURL, "application/json", bytes.NewBuffer(body))
	if err != nil {
		return Result{}
	}

	if resp.StatusCode != http.StatusOK {
		log.Fatalf("error sending req: %s", resp.Status)
	}

	return Result{}
}
