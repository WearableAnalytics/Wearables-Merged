package config

import (
	"log"
	"os"
	"path"
	"testing"
)

func TestParseConfig(t *testing.T) {
	// MQTT
	filepath := path.Join("test-configs", "client_mqtt.yaml")
	log.Println(filepath)

	data, err := os.ReadFile(filepath)
	if err != nil {
		t.Fatal("mqtt: unexpected error reading from file")
	}

	conf, err := ParseConfig(data)
	if err != nil {
		t.Fatalf("unexpected error parsing the config")
	}
	log.Printf("conf: %v", conf)

	_, err = conf.GenerateWorkload()
	if err != nil {
		t.Fatalf("generating wl failed with err: %v", err)
	}

}
