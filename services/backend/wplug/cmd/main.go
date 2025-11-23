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

	client := clients.NewClient(conf.ClientConfig)
	collector := wplug.NewCollector()

	suppliers, err := wplug.NewSupplier(conf.Messages)
	if err != nil {
		log.Fatalf("%v", err)
	}

	lg.NewConstantExecutor(client, collector, suppliers[0])
}
