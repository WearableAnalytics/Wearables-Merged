package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
)

type Client struct {
	ServerURL string
	AuthToken string
	Client    *http.Client
}

type Result struct{}

func NewClient(serverUrl string, authToken string) *Client {
	return &Client{
		ServerURL: serverUrl,
		AuthToken: authToken,
		Client:    &http.Client{},
	}
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

	// Include HTTP-Headers
	request, err := http.NewRequest("POST", c.ServerURL, bytes.NewBuffer(body))
	if err != nil {
		return Result{}
	}

	request.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.AuthToken))
	request.Header.Set("Content-Type", "application/json")

	resp, err := c.Client.Do(request)
	if err != nil {
		return Result{}
	}

	if resp.StatusCode != http.StatusOK {
		log.Fatalf("error sending req (%v): %s", request, resp.Status)
	}

	return Result{}
}
