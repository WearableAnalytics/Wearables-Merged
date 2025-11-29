package pkg

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"time"

	jsoniter "github.com/json-iterator/go"
)

type HTTPConfig struct {
	host        string
	port        int
	timeout     time.Duration
	contentType string
}

type HTTPClient struct {
	Config         HTTPConfig
	Client         *http.Client
	ResponseWaiter *ResponseWaiter
	JsonFast       jsoniter.API
}

func NewHTTPClientFromParams(host string, port int, timeout time.Duration, contentType string, rw *ResponseWaiter) (*HTTPClient, error) {
	configMap := map[string]interface{}{
		"host":        host,
		"port":        port,
		"timeout":     timeout,
		"contentType": contentType,
	}

	client, err := NewHTTPClientFromConfig(configMap, rw)
	if err != nil {
		return nil, err
	}

	return client, nil
}

func NewHTTPClientFromConfig(configMap map[string]interface{}, rw *ResponseWaiter) (*HTTPClient, error) {
	var config HTTPConfig

	if host, ok := configMap["host"]; ok {
		config.host = host.(string)
	} else {
		return nil, fmt.Errorf("config-map must include host")
	}

	if port, ok := configMap["port"]; ok {
		config.port = port.(int)
	} else {
		return nil, fmt.Errorf("config-map must include port")
	}

	// decimal numbers, each with optional fraction and a unit suffix,
	// such as "300ms", "-1.5h" or "2h45m".
	// Valid time units are "ns", "us" (or "µs"), "ms", "s", "m", "h".
	if timeout, ok := configMap["timeout"]; ok {
		dur, err := time.ParseDuration(timeout.(string))
		if err != nil {
			return nil, fmt.Errorf("parsing duration faild with err: %v", err)
		}
		config.timeout = dur
	} else {
		config.timeout = 10 * time.Second
	}

	if contentType, ok := configMap["contentType"]; ok {
		config.contentType = contentType.(string)
	} else {
		config.contentType = "application/json"
	}

	client := &http.Client{
		Timeout: config.timeout,
	}

	return &HTTPClient{
		Config:         config,
		Client:         client,
		ResponseWaiter: rw,
	}, nil
}

func (c HTTPClient) CallEndpoint(ctx context.Context, req Message) Response {
	start := time.Now()

	waiterCh := c.ResponseWaiter.Register(req.DeviceInfo.DeviceID)

	b, err := c.JsonFast.Marshal(req)
	if err != nil {
		return Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: -1,
		}
	}

	url := fmt.Sprintf("https://%s:%d", c.Config.host, c.Config.port)

	body := bytes.NewReader(b)

	send := time.Now()
	resp, err := c.Client.Post(url, c.Config.contentType, body)
	if err != nil {
		return Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: len(b),
		}
	}

	if resp.StatusCode != 200 {
		return Response{
			Timestamp:   start,
			Err:         fmt.Errorf("recieved statuscode: %d", resp.StatusCode),
			Latency:     time.Since(start),
			MessageSize: len(b),
		}
	}

	select {
	case <-waiterCh:
		return Response{
			Timestamp:   start,
			Err:         nil,
			Latency:     time.Since(send),
			MessageSize: len(b),
		}
	case <-ctx.Done():
		return Response{
			Timestamp:   start,
			Err:         fmt.Errorf("context done"),
			Latency:     time.Since(send),
			MessageSize: len(b),
		}
	}
}
