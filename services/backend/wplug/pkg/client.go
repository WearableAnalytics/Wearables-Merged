package pkg

import (
	"context"
	"fmt"
	"log"
	"time"

	paho "github.com/eclipse/paho.mqtt.golang"
	"github.com/google/uuid"
)

// Config:
// client:
// 	type: mqtt
// 	config: # -> Split the config here and pass until
//		topic: "topic"
//		broker: "broker-IP"
//		qos: 0
//---

type MQTTConfig struct {
	Topic  string `yaml:"topic,omitempty"`
	Broker string `yaml:"broker,omitempty"`
	QoS    int    `yaml:"qos,omitempty"`
}

type MQTTClient struct {
	Config MQTTConfig
	client paho.Client
}

func NewMQTTClientFromParams(topic string, broker string, qos int) *MQTTClient {
	configMap := map[string]interface{}{
		"topic":  topic,
		"broker": broker,
		"qos":    qos,
	}

	c, err := NewMQTTClient(configMap)
	if err != nil {
		log.Printf("unexpected error creating new mqtt client")
		return nil
	}

	return c
}

func NewMQTTClient(configMap map[string]interface{}) (*MQTTClient, error) {
	var config MQTTConfig
	config.Topic = "NaN"
	config.Broker = "NaN"
	config.QoS = -1

	for key, val := range configMap {
		if key == "topic" {
			config.Topic = val.(string)
		}
		if key == "broker" {
			// Could do some regex
			config.Broker = val.(string)
		}
		if key == "qos" {
			config.QoS = val.(int)
		}
	}

	if config.Topic == "NaN" || config.Broker == "NaN" || config.QoS == -1 {
		return nil, fmt.Errorf("required fields: topic, broker, qos")
	}

	opts := paho.NewClientOptions()
	opts.SetClientID(uuid.New().String())
	opts.AddBroker(config.Broker)
	opts.SetCleanSession(true)
	opts.SetWriteTimeout(3 * time.Second) // can be tuned in the future

	client := paho.NewClient(opts)

	return &MQTTClient{
		Config: config,
		client: client,
	}, nil
}

func (c MQTTClient) CallEndpoint(ctx context.Context, req Message) Response {
	start := time.Now()
	token := c.client.Publish(c.Config.Topic, byte(c.Config.QoS), false, req)

	token.Wait()

	if token.Error() != nil {
		return Response{
			Err:     token.Error(),
			Latency: time.Since(start),
		}
	}

	return Response{
		Err:     nil,
		Latency: time.Since(start),
	}
}
