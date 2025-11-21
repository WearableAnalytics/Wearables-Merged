package wplug

import (
	"os"
	"path"
	"testing"
)

func TestParseYAML(t *testing.T) {
	p := path.Join("config.test.yaml")

	file, err := os.ReadFile(p)
	if err != nil {
		t.Errorf("unexpected error reading file: %v", err)
	}

	cfg, err := ParseYAML(file)
	if err != nil {
		t.Errorf("unexpected error reading file: %v", err)
	}

	if len(cfg.Messages) != 1 {
		t.Errorf("amout of message type should be 1 is %d", len(cfg.Messages))
	}

	for _, m := range cfg.Messages {
		if m.Schema == "" {
			t.Errorf("error finding schema")
		}
	}
}
