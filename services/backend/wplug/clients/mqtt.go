package clients

import (
	"context"
	"wplug"

	// lg "github.com/luccadibe/go-loadgen"
	paho "github.com/eclipse/paho.mqtt.golang"
	"github.com/google/uuid"
)

type MQTTConfig struct {
	Topic  string
	Broker string
}

type MQTTClient struct {
	Client paho.Client
	conf   MQTTConfig
}

func NewMQTTClient(topic string, broker string) MQTTClient {
	var mqttClient MQTTClient
	var config MQTTConfig

	config.Topic = topic
	config.Broker = broker

	u := uuid.New().String()

	opts := paho.NewClientOptions()
	opts.SetClientID(u)
	opts.AddBroker(broker)

	opts.SetAutoReconnect(true)
	opts.SetCleanSession(true)

	mqttClient.Client = paho.NewClient(opts)
	mqttClient.conf = config

	return mqttClient
}

func (c MQTTClient) CallEndpoint(ctx context.Context, req wplug.Request) wplug.Response {
	token := c.Client.Publish(c.conf.Topic, 2, false, req.Message)
	if token.Error() != nil {
		return wplug.Response{Err: token.Error()}
	}

	return wplug.Response{}
}
