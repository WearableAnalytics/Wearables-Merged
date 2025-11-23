package main

import (
	"log"
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

	// TODO: implement client correctly
	client := clients.NewClient(conf.ClientConfig)
	// TODO: implement collector
	collector := wplug.NewCollector()

	suppliers, err := wplug.NewSupplier(conf.Messages)
	if err != nil {
		log.Fatalf("%v", err)
	}

	_ = lg.NewConstantExecutor(client, collector, suppliers[0])
}
