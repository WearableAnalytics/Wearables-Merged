package main

import (
	"context"
	"log"
	"os"
	"path"
	"time"
	"wplug/pkg"

	go_loadgen "github.com/luccadibe/go-loadgen"
	"github.com/urfave/cli/v3"
)

var workloadFlag = &cli.StringFlag{
	Name:    "workload",
	Usage:   "defines a workload (options: smoke/average)",
	Value:   "smoke",
	Aliases: []string{"w"},
}

var exampleFlag = &cli.BoolFlag{
	Name:    "example",
	Usage:   "defines if the example should be used or the yaml-config",
	Value:   true,
	Aliases: []string{"e"},
}

var maxSizeFlag = &cli.IntFlag{
	Name:    "message-size",
	Usage:   "defines the maximum size of generated messages in bytes (please be careful)",
	Value:   500,
	Aliases: []string{"m"},
}

var virtualUserFlag = &cli.IntFlag{
	Name:    "vu",
	Usage:   "defines the number of virtual users",
	Value:   10,
	Aliases: []string{"v"},
}

func main() {
	log.SetPrefix("wplug: ")
	log.SetFlags(log.Lshortfile | log.LstdFlags)

	cmd := &cli.Command{
		Name:  "wplug",
		Usage: "Generate synthetic load",
		Flags: []cli.Flag{
			workloadFlag,
			exampleFlag,
			maxSizeFlag,
			virtualUserFlag,
		},
		Action: func(ctx context.Context, command *cli.Command) error {
			workload := command.String("workload")
			example := command.Bool("example")
			maxSize := command.Int("message-size")
			vu := command.Int("vu")

			if !example {
				log.Fatalf("currently not supported")
			}

			provider := pkg.NewExampleProvider(vu, maxSize)
			// This need to be switched
			client := pkg.NewMQTTClientFromParams("wearables/#/datax", "tcp://localhost:1883", 0)

			collector, err := go_loadgen.NewCSVCollector[pkg.Response](path.Join("example", "test.csv"), 1*time.Second)
			if err != nil {
				return err
			}

			var wl *pkg.Workload

			switch workload {
			case "smoke":
				wl = pkg.NewSmoke(client, *provider, collector)
			case "average":
				wl = pkg.NewAverageLoad(client, *provider, collector)
			default:
				log.Fatalf("this preset is not supported")
			}

			err = wl.GenerateWorkload()
			if err != nil {
				log.Fatalf("generating workload failed with err")
			}

			return nil
		},
	}

	if err := cmd.Run(context.Background(), os.Args); err != nil {
		log.Fatal(err)
	}

}
