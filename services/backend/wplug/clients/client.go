package clients

import (
	"wplug"

	go_loadgen "github.com/luccadibe/go-loadgen"
)

// Client represents a wrapper interface which wraps the specific types.
type Client interface {
	MQTTClient | HTTPClient
}

// NewClient takes a clientConfig and creates the client based on the type, and returns the client
func NewClient(clientConfig wplug.ClientConfig) go_loadgen.Client[wplug.Request, wplug.Response] {
	return nil
}
