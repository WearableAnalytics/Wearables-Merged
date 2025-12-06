package plot

import (
	"path"
	"testing"
)

func TestPlotter_GeneratePlots(t *testing.T) {
	p := Plotter{
		InputPath:    path.Join("..", "example", "test.csv"),
		OutputFolder: path.Join("..", "plots"),
	}

	err := p.GeneratePlots()
	if err != nil {
		t.Fatal(err)
	}
}
