package main

import (
	"bench/pkg"
	"flag"
	"log"
)

func main() {

	log.SetFlags(log.Lshortfile | log.LstdFlags)

	configPath := flag.String("c", "config.yaml", "path to configuration file")
	flag.StringVar(configPath, "config", "config.yaml", "path to configuration file")
	flag.Parse()

	cfg, err := pkg.LoadConfig(*configPath)
	if err != nil {
		log.Fatalf("failed to load config: %v", err)
	}

	r, err := pkg.NewRunner(cfg)
	if err != nil {
		log.Fatalf("failec to create runner: %v", err)
	}
	defer r.Close()

	log.Printf("runner starting...")
	if err := r.Run(); err != nil {
		log.Fatalf("runner failed: %v", err)
	}

	log.Printf("runner completed")
}
