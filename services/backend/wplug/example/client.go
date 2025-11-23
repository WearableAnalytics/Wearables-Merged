package example

import "context"

type ExampleMQTTClient struct {
	Topic  string
	Broker string
	QoS    int // should be 0 or 2

	// TOD
}

func (e ExampleMQTTClient) CallEndpoint(ctx context.Context, req Message) Response {
	//TODO
	return Response{}
}
