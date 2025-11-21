package wplug

import (
	"fmt"

	"github.com/goccy/go-yaml"
)

type Config struct {
	// Other config needed for the client
	Messages []MessageConfig `yaml:"messages,omitempty"`
}

type MessageConfig struct {
	Schema    string           `yaml:"schema,omitempty"`
	Constants []ConstantConfig `yaml:"constants,omitempty"`
	Variables []VariableConfig `yaml:"variables,omitempty"`
}

type ConstantConfig struct {
	Name  string      `yaml:"name,omitempty"`
	Value interface{} `yaml:"value,omitempty"` // How will the compiler handle that efficiently?
}

type VariableConfig struct {
	Name      string          `yaml:"name,omitempty"`
	Generator GeneratorConfig `yaml:"generator,omitempty"`
}

// GeneratorConfig is a configuration of a Service which creates actual values based on given bounds.
// It can be just one of those
type GeneratorConfig struct {
	NumericGenerator NumericGeneratorConfig `yaml:"numeric-generator,omitempty"`
	TimeGenerator    TimeGeneratorConfig    `yaml:"time-generator,omitempty"`
	UuidGenerator    UuidGeneratorConfig    `yaml:"uuid-generator,omitempty"`
}

type NumericGeneratorConfig struct {
	Base float64 `yaml:"base,omitempty"`
	Amp  float64 `yaml:"amp,omitempty"`
}

type TimeGeneratorConfig struct {
	Type   string `yaml:"type,omitempty"`
	Format string `yaml:"format,omitempty"`
}

type UuidGeneratorConfig struct{}

// ParseYAML takes an encoded `.yaml` file and maps them to the config, used for generating the client
func ParseYAML(data []byte) (*Config, error) {
	var config Config

	if err := yaml.UnmarshalWithOptions(data, &config, yaml.Strict()); err != nil {
		return nil, err
	}

	// validate yaml config
	if err := validateConfig(&config); err != nil {
		return nil, err
	}

	return &config, nil
}

func validateConfig(cfg *Config) error {
	if cfg == nil {
		return fmt.Errorf("config is nil")
	}

	if len(cfg.Messages) == 0 {
		return fmt.Errorf("must specify at least one message type")
	}

	for i, m := range cfg.Messages {
		if err := validateMessage(&m); err != nil {
			return fmt.Errorf("%d. message caused: %v", i, err)
		}
	}

	return nil
}

func validateMessage(m *MessageConfig) error {
	if m.Schema == "" {
		return fmt.Errorf("must provide a schema for the message")
	}
	// You could validate the schema but I don't care (will be buggy at runtime, I guess)
	for i, c := range m.Constants {
		if err := validateConstant(&c); err != nil {
			return fmt.Errorf("%d. constant caused: %v", i, err)
		}
	}

	for i, v := range m.Variables {
		if err := validateVariable(&v); err != nil {
			return fmt.Errorf("%d. variable caused: %v", i, err)
		}
	}

	return nil
}

func validateConstant(c *ConstantConfig) error {
	if c.Name == "" {
		return fmt.Errorf("constant missing name")
	}

	switch c.Value.(type) {
	case string, int, float32, float64, bool:
	default:
		return fmt.Errorf("type is unknown")
	}

	return nil
}

func validateVariable(v *VariableConfig) error {
	if v.Name == "" {
		return fmt.Errorf("variable missing name")
	}

	// TODO: validate Generators

	return nil
}
