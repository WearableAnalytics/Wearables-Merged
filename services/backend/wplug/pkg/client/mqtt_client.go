package client

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"
	"wplug/pkg/message"
	"wplug/pkg/waiter"

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
	QoS    uint64 `yaml:"qos,omitempty"`
}

type MQTTClient struct {
	Config   MQTTConfig
	opts     *paho.ClientOptions
	rw       *waiter.ResponseWaiter
	JsonFast jsoniter.API
}

func NewMQTTClientFromParams(topic string, broker string, qos int, rw *waiter.ResponseWaiter) *MQTTClient {
	configMap := map[string]interface{}{
		"topic":  topic,
		"broker": broker,
		"qos":    qos,
	}

	c, err := NewMQTTClient(configMap, rw)
	if err != nil {
		log.Printf("unexpected error creating new mqtt client")
		return nil
	}

	return c
}

func NewMQTTClient(configMap map[string]interface{}, rw *waiter.ResponseWaiter) (*MQTTClient, error) {
	var config MQTTConfig
	config.Topic = "NaN"
	config.Broker = "NaN"
	config.QoS = 3

	for key, val := range configMap {
		if key == "topic" {
			config.Topic = val.(string)
		}
		if key == "broker" {
			// Could do some regex
			config.Broker = val.(string)
		}
		if key == "qos" {
			config.QoS = val.(uint64)
		}
	}

	if config.Topic == "NaN" || config.Broker == "NaN" || config.QoS == 3 {
		return nil, fmt.Errorf("required fields: topic, broker, qos")
	}

	jsonFast := jsoniter.ConfigFastest

	opts := paho.NewClientOptions()
	opts.SetClientID(uuid.New().String())
	opts.AddBroker(config.Broker)
	opts.SetCleanSession(true)
	opts.SetWriteTimeout(3 * time.Second) // can be tuned in the future

	//client := paho.NewClient(opts)

	log.Printf("mqtt client created and connected!")

	return &MQTTClient{
		Config:   config,
		rw:       rw,
		opts:     opts,
		JsonFast: jsonFast,
	}, nil
}

func (c MQTTClient) CreateAndConnect() (paho.Client, error) {
	client := paho.NewClient(c.opts)
	conn := client.Connect()
	conn.Wait()

	if conn.Error() != nil {
		return nil, conn.Error()
	}

	return client, nil
}

func (c MQTTClient) CallEndpoint(ctx context.Context, req message.Message) message.Response {
	start := time.Now()

	var client paho.Client
	client, err := c.CreateAndConnect()
	if err != nil {
		return message.Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: -1,
		}
	}
	defer client.Disconnect(1)

	waiterCh := c.rw.Register(req.DeviceInfo.DeviceID)

	b, err := c.JsonFast.Marshal(req)
	if err != nil {
		return message.Response{
			Timestamp:   start,
			Err:         err,
			Latency:     time.Since(start),
			MessageSize: -1,
		}
	}

	topicArray := strings.Split(c.Config.Topic, "/")
	topicArray[1] = req.DeviceInfo.DeviceID
	topic := fmt.Sprintf("%s/%s/%s", topicArray[0], topicArray[1], topicArray[2])

	send := time.Now().UnixNano()

	if client.IsConnectionOpen() {

		token := client.Publish(topic, 1, false, b)
		token.Wait()

		if token.Error() != nil {
			log.Printf("publish failed with err: %v", token.Error())
			return message.Response{
				Timestamp:   start,
				Err:         token.Error(),
				Latency:     time.Since(start),
				MessageSize: -1,
			}
		}
	}
	log.Println("publish successful")

	select {
	case <-waiterCh:
		latencyNs := time.Now().UnixNano() - send // Could also measure the kafka
		return message.Response{
			Timestamp:   start,
			Err:         nil,
			Latency:     time.Duration(latencyNs),
			MessageSize: len(b),
		}
	case <-ctx.Done():
		return message.Response{
			Timestamp: start,
			Err:       fmt.Errorf("timeout waiting for kafka"),
			Latency:   time.Since(start),
		}
	}
}
