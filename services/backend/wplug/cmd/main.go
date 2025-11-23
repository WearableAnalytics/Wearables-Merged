package main

import (
	"context"
	"log"
	"os"
	example2 "wplug/example"

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

var maxSizeFlag = &cli.Int32Flag{
	Name:    "message-size",
	Usage:   "defines the maximum size of generated messages in bytes (please be careful)",
	Value:   500,
	Aliases: []string{"m"},
}

var virtualUserFlag = &cli.Int16Flag{
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
			maxSize := command.Int32("message-size")
			vu := command.Int16("vu")

			if !example {
				log.Fatalf("currently not supported")
			}

			example2.NewExampleProvider(vu, maxSize)

			switch workload {
			case "smoke":
			case "average":
			default:
				log.Fatalf("this preset is not supported")
			}

			return nil
		},
	}

	if err := cmd.Run(context.Background(), os.Args); err != nil {
		log.Fatal(err)
	}

}
