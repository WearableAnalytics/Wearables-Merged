package main

import (
	"log"
	"wplug"
	"wplug/clients"

	lg "github.com/luccadibe/go-loadgen"
)

// flags -> paths

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

	lg.NewConstantExecutor(client, collector)
}
