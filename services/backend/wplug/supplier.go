package wplug

import (
	"encoding/json"
	"os"
)

// We need to generate a JSON based from

type Supplier struct {
	Schema    string // Path to JSON Schema
	RawSchema RawSchema
	// Base
	Constants map[string]interface{}
	Variables map[string]Generator
}

type RawSchema map[string]interface{}

type BaseJson map[string]interface{}

func NewSupplier(schemaPath string, constants map[string]interface{}, variables map[string]Generator) (*Supplier, error) {
	var supplier Supplier

	// Resolve Schema
	s, err := BuildSchema(schemaPath)
	if err != nil {
		return nil, err
	}

	supplier.RawSchema = s
	supplier.Constants = constants
	supplier.Variables = variables

	// Generate Base JSON from that -> set fields except the Variables

	return &supplier, nil
}

func BuildSchema(schemaPath string) (map[string]interface{}, error) {
	var s RawSchema

	data, err := os.ReadFile(schemaPath)
	if err != nil {
		return nil, err
	}

	if err = json.Unmarshal(data, &s); err != nil {
		return nil, err
	}

	return s, nil
}

func GenerateBaseJSON(schema map[string]interface{}) interface{} {
	t, _ := schema["type"].(string)

	// Switching on Types is crazy, but fuck it
	switch t {
	case "object":
		result := map[string]interface{}{}
		properties, _ := schema["properties"].(map[string]interface{})
		required, _ := schema["required"].([]interface{})

		for _, field := range required {
			name := field.(string)
			if propSchema, ok := properties[name]; ok {
				result[name] = GenerateBaseJSON(propSchema.(map[string]interface{}))
			}
		}
		return result

	case "string":
		return "string"

	case "number":
		return 0

	case "integer":
		return 0

	case "boolean":
		return false

	case "array":
		items, _ := schema["items"].(map[string]interface{})
		return []interface{}{GenerateBaseJSON(items)}

	default:
		return nil
	}
}

type Generator interface{}

func (s Supplier) GetData() Request {
	// We need to use the provided information from the YAML

	// Set Constants
	// Generate Variables
	// Encode JSON into []byte
	// return []byte

	return Request{}
}
