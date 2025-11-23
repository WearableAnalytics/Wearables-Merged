package main

import (
	"context"
	"log"
	"os"

	"github.com/urfave/cli/v3"
)

var workloadFlag = &cli.StringFlag{
	Name:    "workload",
	Usage:   "define a workload (options: smoke/average)",
	Value:   "smoke",
	Aliases: []string{"w"},
}

var exampleFlag = &cli.BoolFlag{
	Name:    "example",
	Usage:   "define if the example should be used or the yaml-config",
	Value:   true,
	Aliases: []string{"e"},
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
		},
		Action: func(ctx context.Context, command *cli.Command) error {
			workload := command.String("workload")
			example := command.Bool("example")

			if !example {
				log.Fatalf("currently not supported")
			}

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
