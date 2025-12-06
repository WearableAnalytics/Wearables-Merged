package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"
	"wplug/pkg/message"
	"wplug/pkg/waiter"

	jsoniter "github.com/json-iterator/go"
)

type HTTPConfig struct {
	Url          string
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

	if host, ok := configMap["url"]; ok {
		config.Url = host.(string)
	} else {
		return nil, fmt.Errorf("config-map must include host")
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

	b, err := json.Marshal(req)
	if err != nil {
		return message.Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: -1,
		}
	}

	body := bytes.NewReader(b)

	send := time.Now()
	log.Println(string(b))

	if json.Valid(b) {
		log.Printf("is valid json")
	}

	resp, err := c.Client.Post(c.Config.Url, c.Config.ContentType, body)
	if err != nil {
		return message.Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: len(b),
		}
	}

	buf := new(bytes.Buffer)
	_, err = buf.ReadFrom(resp.Body)
	if err != nil {
		return message.Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: len(b),
		}
	}

	respBodyStr := buf.String()

	if resp.StatusCode != 200 {
		return message.Response{
			Timestamp:   start,
			Err:         fmt.Errorf("recieved statuscode: %d with resp: %v, body: %s", resp.StatusCode, resp.Status, respBodyStr),
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
