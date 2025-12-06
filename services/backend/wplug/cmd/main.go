package main

import (
	"context"
	"log"
	"os"
	"wplug/pkg/config"

	"github.com/urfave/cli/v3"
)

var configFlag = &cli.StringFlag{
	Name:    "config",
	Usage:   "path to config file",
	Value:   "config.yaml",
	Aliases: []string{"c", "cfg"},
}

func main() {
	log.SetPrefix("wplug: ")
	log.SetFlags(log.Lshortfile | log.LstdFlags)

	cmd := &cli.Command{
		Name:  "wplug",
		Usage: "Generate synthetic load",
		Flags: []cli.Flag{
			configFlag,
		},
		Action: func(ctx context.Context, command *cli.Command) error {
			filepath := command.String("config")

			data, err := os.ReadFile(filepath)
			if err != nil {
				return err
			}

			conf, err := config.ParseConfig(data)
			if err != nil {
				return err
			}

			err = conf.StartLoadGeneration(ctx)
			if err != nil {
				return err
			}

			return nil
		},
	}

	if err := cmd.Run(context.Background(), os.Args); err != nil {
		log.Fatal(err)
	}

}
