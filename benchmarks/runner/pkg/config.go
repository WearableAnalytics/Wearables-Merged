package pkg

import (
	"os"
	"path/filepath"
	"strings"

	go_yaml "github.com/goccy/go-yaml"
)

type Config struct {
	SSH     SSHConfig  `yaml:"ssh"`
	Job     JobConfig  `yaml:"job"`
	Paths   PathConfig `yaml:"paths"`
	Timeout string     `yaml:"timeout"`
}

type SSHConfig struct {
	User    string `yaml:"user"`
	Host    string `yaml:"host"`
	KeyPath string `yaml:"keyPath"`
}

type JobConfig struct {
	Name      string `yaml:"name"`
	Namespace string `yaml:"namespace"`
}

type PathConfig struct {
	LocalConfig  string `yaml:"localConfig"`
	RemoteConfig string `yaml:"remoteConfig"`
	LocalOutput  string `yaml:"localOutput,omitempty"`
	LocalLogs    string `yaml:"localLogs,omitempty"`
}

func LoadConfig(path string) (*Config, error) {
	var cfg Config

	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	if err := go_yaml.UnmarshalWithOptions(data, &cfg, go_yaml.Strict()); err != nil {
		return nil, err
	}

	cfg.SSH.KeyPath = expandPath(cfg.SSH.KeyPath)

	return &cfg, nil
}

func expandPath(path string) string {
	if strings.HasPrefix(path, "~/") {
		home, err := os.UserHomeDir()
		if err != nil {
			return path
		}

		return filepath.Join(home, path[2:])
	}

	return path
}
