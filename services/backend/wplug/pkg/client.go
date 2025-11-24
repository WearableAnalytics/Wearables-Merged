package pkg

import (
	"context"
	"errors"
	"fmt"
	"log"
	"strings"
	"time"

	paho "github.com/eclipse/paho.mqtt.golang"
	"github.com/google/uuid"
	jsoniter "github.com/json-iterator/go"
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
	Config   MQTTConfig
	client   paho.Client
	JsonFast jsoniter.API
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

	jsonFast := jsoniter.ConfigFastest

	opts := paho.NewClientOptions()
	opts.SetClientID(uuid.New().String())
	opts.AddBroker(config.Broker)
	opts.SetCleanSession(true)
	opts.SetWriteTimeout(3 * time.Second) // can be tuned in the future

	client := paho.NewClient(opts)

	log.Printf("mqtt client created and connected!")

	return &MQTTClient{
		Config:   config,
		client:   client,
		JsonFast: jsonFast,
	}, nil
}

func (c MQTTClient) CallEndpoint(ctx context.Context, req Message) Response {
	start := time.Now()
	conn := c.client.Connect()
	conn.Wait()

	if conn.Error() != nil {
		return Response{
			Timestamp:   start,
			Err:         conn.Error(),
			Latency:     time.Since(start),
			MessageSize: -1,
		}
	}
	b, err := c.JsonFast.Marshal(req)
	if err != nil {
		return Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: -1,
		}
	}

	topicArray := strings.Split(c.Config.Topic, "/")
	topicArray[1] = req.DeviceInfo.DeviceID
	topic := fmt.Sprintf("%s/%s/%s", topicArray[0], topicArray[1], topicArray[2])

	token := c.client.Publish(topic, byte(c.Config.QoS), false, b)

	token.Wait()

	if token.Error() != nil {
		return Response{
			Timestamp:   start,
			Err:         token.Error(),
			Latency:     time.Since(start),
			MessageSize: -1,
		}
	}

	return Response{
		Timestamp:   start,
		Err:         errors.New(""),
		Latency:     time.Since(start),
		MessageSize: len(b),
	}
}
