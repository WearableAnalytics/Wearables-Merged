package main

import (
	"log"
	"path"
	"wplug"
	"wplug/clients"

	lg "github.com/luccadibe/go-loadgen"
)

func main() {
	log.SetPrefix("wplug: ")
	log.SetFlags(log.LstdFlags | log.Lshortfile)

	// Create Client
	conf, err := wplug.ParseYAML([]byte{})
	if err != nil {
		log.Fatalf("%v", err)
	}

	// Start from Config

	client, err := clients.NewClient(conf.ClientConfig)
	if err != nil {
		log.Fatalf("%v", err)
	}

	collector, err := lg.NewCSVCollector[wplug.Response](path.Join("csvs", "example.csv"), 1)
	if err != nil {
		log.Fatalf("%v", err)
	}

	suppliers, err := wplug.NewSupplier(conf.Messages)
	if err != nil {
		log.Fatalf("%v", err)
	}

	_ = lg.NewConstantExecutor(client, collector, suppliers[0])

}
