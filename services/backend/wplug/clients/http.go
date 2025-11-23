package clients

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"time"
	"wplug"
)

type HTTPConfig struct {
	Url         string
	ContentType string
}

type HTTPClient struct {
	conf HTTPConfig
}

type HttpResponse struct {
	StatusCode int
	Body       io.Reader
}

func (c HTTPClient) CallEndpoint(ctx context.Context, req wplug.Request) wplug.Response {
	start := time.Now()
	resp, err := http.Post(c.conf.Url, "application/json", bytes.NewReader(req.Message))
	if err != nil {
		return wplug.Response{Err: err, Latency: time.Since(start)}
	}

	return wplug.Response{Message: resp.Body, Err: nil, Latency: time.Since(start)}
}
