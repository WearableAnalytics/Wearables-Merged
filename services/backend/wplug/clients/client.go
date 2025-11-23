package clients

import (
	"fmt"
	"wplug"

	go_loadgen "github.com/luccadibe/go-loadgen"
)

// Client represents a wrapper interface which wraps the specific types.
type Client interface {
	MQTTClient | HTTPClient
}

// NewClient takes a clientConfig and creates the client based on the type, and returns the client
func NewClient(clientConfig wplug.ClientConfig) (go_loadgen.Client[wplug.Request, wplug.Response], error) {
	switch clientConfig.Type {
	case "mqtt":
		c, err := NewMQTTClientFromConfigMap(clientConfig.Config)
		if err != nil {
			return nil, err
		}
		return c, nil
	case "http":
		c, err := NewHTTPClientFromConfigMap(clientConfig.Config)
		if err != nil {
			return nil, err
		}
		return c, nil
	default:
		return nil, fmt.Errorf("not supported client config")
	}
}
