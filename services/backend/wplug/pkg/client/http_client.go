package client

import (
	"bytes"
	"context"
	"fmt"
	"log"
	"net/http"
	"time"
	"wplug/pkg/message"
	"wplug/pkg/waiter"

	jsoniter "github.com/json-iterator/go"
)

type HTTPConfig struct {
	Host         string
	Port         uint64
	Timeout      time.Duration
	ContentType  string
	ConsumeKafka bool
}

type HTTPClient struct {
	Config         HTTPConfig
	Client         *http.Client
	ResponseWaiter *waiter.ResponseWaiter
	JsonFast       jsoniter.API
}

func NewHTTPClientFromParams(host string, port int, timeout time.Duration, contentType string, consumeKafka bool, rw *waiter.ResponseWaiter) (*HTTPClient, error) {
	configMap := map[string]interface{}{
		"host":          host,
		"port":          port,
		"timeout":       timeout,
		"content-type":  contentType,
		"consume-kafka": consumeKafka,
	}

	client, err := NewHTTPClientFromConfig(configMap, rw)
	if err != nil {
		return nil, err
	}

	return client, nil
}

func NewHTTPClientFromConfig(configMap map[string]interface{}, rw *waiter.ResponseWaiter) (*HTTPClient, error) {
	var config HTTPConfig

	if host, ok := configMap["host"]; ok {
		config.Host = host.(string)
	} else {
		return nil, fmt.Errorf("config-map must include host")
	}

	if port, ok := configMap["port"]; ok {
		config.Port = port.(uint64)
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
		config.Timeout = dur
	} else {
		config.Timeout = 10 * time.Second
	}

	if contentType, ok := configMap["content-type"]; ok {
		config.ContentType = contentType.(string)
	} else {
		config.ContentType = "application/json"
	}

	client := &http.Client{
		Timeout: config.Timeout,
	}

	if consumeKafka, ok := configMap["consume-kafka"]; ok {
		config.ConsumeKafka = consumeKafka.(bool)
	} else {
		config.ConsumeKafka = true
	}

	return &HTTPClient{
		Config:         config,
		Client:         client,
		ResponseWaiter: rw,
		JsonFast:       jsoniter.ConfigFastest,
	}, nil
}

func (c HTTPClient) CallEndpoint(ctx context.Context, req message.Message) message.Response {
	start := time.Now()

	waiterCh := c.ResponseWaiter.Register(req.DeviceInfo.DeviceID)
	log.Printf("c.Client = %v, c.Conf = %v, rw: %v, jsonFast: %v", c.Client, c.Config, c.ResponseWaiter, c.JsonFast)
	log.Printf("http: before marshalling: req: %v", req)
	b, err := c.JsonFast.Marshal(req)
	if err != nil {
		return message.Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: -1,
		}
	}

	url := fmt.Sprintf("https://%s:%d", c.Config.Host, c.Config.Port)

	body := bytes.NewReader(b)

	send := time.Now()
	resp, err := c.Client.Post(url, c.Config.ContentType, body)
	if err != nil {
		return message.Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: len(b),
		}
	}

	if resp.StatusCode != 200 {
		return message.Response{
			Timestamp:   start,
			Err:         fmt.Errorf("recieved statuscode: %d", resp.StatusCode),
			Latency:     time.Since(start),
			MessageSize: len(b),
		}
	}

	// So we can generate load from without the need of consuming from kafka (for the beginning)
	if c.Config.ConsumeKafka == false {
		return message.Response{
			Timestamp:   start,
			Err:         nil,
			Latency:     time.Since(start),
			MessageSize: len(b),
		}
	}

	select {
	case <-waiterCh:
		return message.Response{
			Timestamp:   start,
			Err:         nil,
			Latency:     time.Since(send),
			MessageSize: len(b),
		}
	case <-ctx.Done():
		return message.Response{
			Timestamp:   start,
			Err:         fmt.Errorf("context done"),
			Latency:     time.Since(send),
			MessageSize: len(b),
		}
	}
}
