package clients

import (
	"bytes"
	"context"
	"fmt"
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

func NewHTTPClientFromConfigMap(configMap map[string]interface{}) (HTTPClient, error) {
	var url string
	var contentType string

	for key, val := range configMap {
		switch key {
		case "url":
			// validate
			url = val.(string)
		case "content-type":
			contentType = "application/json" //val.(string)
		default:
			return HTTPClient{}, fmt.Errorf("unsupported key: %s", key)
		}
	}

	if url == "" || contentType == "" {
		return HTTPClient{}, fmt.Errorf("missing url or content-type")
	}

	conf := HTTPConfig{
		Url:         url,
		ContentType: contentType,
	}

	return HTTPClient{conf: conf}, nil
}

func (c HTTPClient) CallEndpoint(ctx context.Context, req wplug.Request) wplug.Response {
	start := time.Now()
	resp, err := http.Post(c.conf.Url, c.conf.ContentType, bytes.NewReader(req.Message))
	if err != nil {
		return wplug.Response{Err: err, Latency: time.Since(start)}
	}

	return wplug.Response{Message: resp.Body, Err: nil, Latency: time.Since(start)}
}
