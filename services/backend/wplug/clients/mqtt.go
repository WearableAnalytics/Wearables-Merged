package clients

import (
	"context"
	"fmt"
	"time"
	"wplug"

	// lg "github.com/luccadibe/go-loadgen"
	paho "github.com/eclipse/paho.mqtt.golang"
	"github.com/google/uuid"
)

type MQTTConfig struct {
	Topic  string
	Broker string
	QoS    byte
}

type MQTTClient struct {
	Client paho.Client
	conf   MQTTConfig
}

func NewMQTTClientFromConfigMap(configMap map[string]interface{}) (MQTTClient, error) {
	var topic, broker string
	qos := -1

	for key, val := range configMap {
		switch key {
		case "topic":
			// validate maybe
			topic = val.(string)
		case "broker":
			// add validation regex
			broker = val.(string)
		case "qos":
			// add validation
			qos = val.(int)
		default:
			return MQTTClient{}, fmt.Errorf("unsupport field: %s in ConfigMap", key)
		}
	}
	if topic == "" {
		return MQTTClient{}, fmt.Errorf("missing field topic")
	}
	if broker == "" {
		return MQTTClient{}, fmt.Errorf("missing field broker")
	}

	if qos < 0 || qos > 2 {
		return MQTTClient{}, fmt.Errorf("missing or wrong field qos")
	}

	return NewMQTTClient(topic, broker, qos), nil
}

func NewMQTTClient(topic string, broker string, qos int) MQTTClient {
	var mqttClient MQTTClient
	var config MQTTConfig

	config.Topic = topic
	config.Broker = broker
	config.QoS = byte(qos)

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
	start := time.Now()
	token := c.Client.Publish(c.conf.Topic, c.conf.QoS, false, req.Message)
	if token.Error() != nil {
		return wplug.Response{Latency: time.Since(start), Err: token.Error()}
	}

	return wplug.Response{Latency: time.Since(start), Err: nil}
}
