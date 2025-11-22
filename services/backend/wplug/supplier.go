package wplug

import (
	"encoding/json"
	"os"
	"strings"
)

// We need to generate a JSON based from

type Supplier struct {
	Schema    string // Path to JSON Schema
	RawSchema map[string]interface{}
	BaseJson  interface{}
	Constants map[string]interface{}
	Variables map[string]Generator
}

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

	baseJson := GenerateBaseJSON(s, constants)
	supplier.BaseJson = baseJson

	return &supplier, nil
}

func ExpandPaths(flat map[string]interface{}) map[string]interface{} {
	root := map[string]interface{}{}

	for path, val := range flat {
		parts := strings.Split(path, ".")
		cursor := root
		for i := 0; i < len(parts)-1; i++ {
			p := parts[i]
			if _, ok := cursor[p]; !ok {
				cursor[p] = map[string]interface{}{}
			}
			cursor = cursor[p].(map[string]interface{})
		}
		cursor[parts[len(parts)-1]] = val
	}
	return root
}

func BuildSchema(schemaPath string) (map[string]interface{}, error) {
	var s map[string]interface{}

	data, err := os.ReadFile(schemaPath)
	if err != nil {
		return nil, err
	}

	if err = json.Unmarshal(data, &s); err != nil {
		return nil, err
	}

	return s, nil
}

func GenerateBaseJSON(schema map[string]interface{}, constants map[string]interface{}, fieldNames ...string) interface{} {
	if len(fieldNames) > 0 {
		name := fieldNames[0]
		if v, ok := constants[name]; ok {
			// If the constant is a primitive → return it immediately.
			switch vv := v.(type) {
			case string, float64, int, bool:
				return vv
			case map[string]interface{}:
				// Continue with this new nested constant map
				constants = vv
			}
		}
	}

	t, _ := schema["type"].(string)

	switch t {
	case "object":
		result := map[string]interface{}{}
		properties, _ := schema["properties"].(map[string]interface{})
		required, _ := schema["required"].([]interface{})

		for _, field := range required {
			name := field.(string)
			if propSchema, ok := properties[name]; ok {
				result[name] = GenerateBaseJSON(propSchema.(map[string]interface{}), constants, name)
			}
		}
		return result

	case "string":
		return "-1"

	case "number":
		return -1

	case "integer":
		return -1

	case "boolean":
		return false

	case "array":
		items, _ := schema["items"].(map[string]interface{})
		return []interface{}{GenerateBaseJSON(items, constants)}

	default:
		return nil
	}
}

func (s Supplier) GetData() Request {
	// We need to use the provided information from the YAML

	// Set Constants
	// Generate Variables
	// Encode JSON into []byte
	// return []byte

	return Request{}
}
