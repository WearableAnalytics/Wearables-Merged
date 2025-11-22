package wplug

import (
	"encoding/json"
	"log"
	"os"
	"strings"
)

type Supplier struct {
	Schema    string // Path to JSON Schema
	RawSchema map[string]interface{}
	BaseJson  interface{}
	Constants map[string]interface{}
	Variables map[string]interface{} // What if we did it differently here
}

func NewSupplier(schemaPath string, constants map[string]interface{}, variables map[string]interface{}) (*Supplier, error) {
	var supplier Supplier

	// Resolve Schema
	s, err := BuildSchema(schemaPath)
	if err != nil {
		return nil, err
	}

	// Enables dotted paths
	constants = ExpandPaths(constants)
	variables = ExpandPaths(variables)

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

func FillMissingFields(base map[string]interface{}, variables map[string]interface{}) map[string]interface{} {
	for key, val := range variables {
		switch gen := val.(type) {
		case map[string]interface{}:
			subBase, ok := base[key].(map[string]interface{})
			if !ok {
				subBase = make(map[string]interface{})
			}
			base[key] = FillMissingFields(subBase, gen)

		// This is for the NumericGenerator
		case Generator[float64]:
			if _, exists := base[key]; exists {
				base[key] = gen.Generate()
			}

		case Generator[string]:
			if _, exists := base[key]; exists {
				base[key] = gen.Generate()
			}

		default:
			log.Fatalf("unknown generator type")
		}
	}

	return base
}

func (s Supplier) GetData() Request {
	res := FillMissingFields(s.BaseJson.(map[string]interface{}), s.Variables)

	msg, err := json.Marshal(res)
	if err != nil {
		return Request{}
	}

	return Request{Message: msg}
}
