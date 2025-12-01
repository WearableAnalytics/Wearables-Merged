package config

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"
	"wplug/pkg/client"
	"wplug/pkg/load"
	"wplug/pkg/message"
	"wplug/pkg/waiter"

	go_yaml "github.com/goccy/go-yaml"
	go_loadgen "github.com/luccadibe/go-loadgen"
)

type ClientConfig struct {
	Type   string                 `yaml:"type"`
	Config map[string]interface{} `yaml:"config"`
}

type WorkloadConfig struct {
	Preset       string `yaml:"preset"`
	VirtualUsers int    `yaml:"vu"`
	MessageSize  int    `yaml:"max-size"`
}

type CollectorConfig struct {
	FilePath      string `yaml:"file"`
	FlushInterval string `yaml:"flush"`
}

type Config struct {
	Client    ClientConfig               `yaml:"client"`
	Kafka     client.KafkaConsumerConfig `yaml:"kafka"`
	Workload  WorkloadConfig             `yaml:"workload"`
	Collector CollectorConfig            `yaml:"collector"`
}

func ParseConfig(data []byte) (*Config, error) {
	var conf Config

	log.Printf("before unmarshal")
	if err := go_yaml.UnmarshalWithOptions(data, &conf, go_yaml.Strict()); err != nil {
		return nil, err
	}
	log.Printf("after unmarshal")
	log.Printf("conf: %v", conf)

	return &conf, nil
}

func (c Config) StartLoadGeneration(ctx context.Context) error {
	wl, err := c.GenerateWorkload()
	if err != nil {
		return err
	}

	kconsumer, err := c.GenerateKafkaConsumer()
	if err != nil {
		return err
	}

	return wl.GenerateWorkload(ctx, kconsumer)
}

func (c Config) GenerateClient() (go_loadgen.Client[message.Message, message.Response], error) {

	switch c.Client.Type {
	case "http":
		rw := waiter.GetResponseWaiter()
		return client.NewHTTPClientFromConfig(c.Client.Config, rw)
	case "mqtt":
		rw := waiter.GetResponseWaiter()
		return client.NewMQTTClient(c.Client.Config, rw)
	default:
		return nil, fmt.Errorf("this client type is not supported")
	}
}

func (c Config) GenerateKafkaConsumer() (*client.KafkaConsumer, error) {
	conf := c.Kafka

	kconsumer := client.NewKafkaConsumer(
		waiter.GetResponseWaiter(),
		conf.Topic,
		conf.Partition,
		conf.MaxBytes,
		conf.Brokers...,
	)

	return kconsumer, nil
}

func (c Config) GenerateCollector() (*go_loadgen.CSVCollector[message.Response], error) {
	conf := c.Collector
	dur, err := time.ParseDuration(conf.FlushInterval)
	if err != nil {
		return nil, err
	}
	return go_loadgen.NewCSVCollector[message.Response](conf.FilePath, dur)
}

func (c Config) GenerateWorkload() (*load.Workload, error) {
	log.Printf("before creating anything")
	conf := c.Workload

	provider := message.NewProvider(conf.VirtualUsers, conf.MessageSize)
	log.Printf("after creating provider")

	collector, err := c.GenerateCollector()
	if err != nil {
		return nil, fmt.Errorf("generating collector failed with err: %v", err)
	}
	log.Printf("after creating collector")

	cl, err := c.GenerateClient()
	if err != nil {
		return nil, err
	}
	log.Printf("after generating client")

	switch strings.ToLower(conf.Preset) {
	case "smoke":
		return load.NewSmoke(cl, *provider, collector), nil
	case "avg":
		return load.NewAverageLoad(cl, *provider, collector), nil
	default:
		return nil, fmt.Errorf("preset not supported")
	}
}
