package clients

import (
	"context"
	"wplug"
)

type HTTPConfig struct{}

type HTTPClient struct{}

func (H HTTPClient) CallEndpoint(ctx context.Context, req wplug.Request) wplug.Response {
	//TODO implement me
	panic("implement me")
}
