package wplug

import (
	"log"
	"path"
	"reflect"
	"testing"
	"time"
)

func TestNewSupplier(t *testing.T) {
	// Test Inputs
	schemaPath := path.Join("test-resources", "test1-schema.json")
	constants := map[string]interface{}{
		"value.__type": "TestType",
		"type":         "TestType",
	}

	tg := NewTimestampGenerator(time.DateTime)
	sng := NewSimpleNumericGenerator(1000.0, 100.0)

	variables := map[string]interface{}{
		"timestamp":           tg,
		"value.numeric_value": sng,
	}

	s, err := NewSupplier(schemaPath, constants, variables)
	if err != nil {
		t.Errorf("unexpected error creating new supplier: %v", err)
	}

	expected := map[string]interface{}{
		"timestamp": "-1",
		"type":      "TestType",
		"unit":      "-1",
		"value": map[string]interface{}{
			"__type":        "TestType",
			"numeric_value": -1,
		},
	}

	expectedVars := map[string]interface{}{
		"timestamp": tg,
		"value": map[string]interface{}{
			"numeric_value": sng,
		},
	}

	if !reflect.DeepEqual(s.BaseJson, expected) {
		t.Errorf("baseJson does not match expected output")
	}

	if !reflect.DeepEqual(expectedVars, s.Variables) {
		t.Errorf("variables does not match expected output")
	}

}

func TestBuildSchema(t *testing.T) {
	p := path.Join("test-resources", "test1-schema.json")

	schema, err := BuildSchema(p)
	if err != nil {
		t.Errorf("unexpected error building schema: %v", err)
	}
	log.Printf("%v", schema)
}

func TestExpandPaths(t *testing.T) {
	input := map[string]interface{}{
		"value.__type": "TestType",
		"type":         "TestType",
	}

	expected := map[string]interface{}{
		"value": map[string]interface{}{
			"__type": "TestType",
		},
		"type": "TestType",
	}

	result := ExpandPaths(input)

	log.Printf("%v", result)

	if !reflect.DeepEqual(result, expected) {
		t.Errorf("ExpandPaths() = %#v, expected %#v", result, expected)
	}
}

func TestGenerateBaseJSON(t *testing.T) {
	// First generate a Schema Map
	p := path.Join("test-resources", "test1-schema.json")

	schema, err := BuildSchema(p)
	if err != nil {
		t.Errorf("unexpected error building schema: %v", err)
	}

	input := map[string]interface{}{
		"value.__type": "TestType",
		"type":         "TestType",
	}

	expandedConstants := ExpandPaths(input)

	result := GenerateBaseJSON(schema, expandedConstants)
	log.Printf("%v", result)

	expected := map[string]interface{}{
		"timestamp": "-1",
		"type":      "TestType",
		"unit":      "-1",
		"value": map[string]interface{}{
			"__type":        "TestType",
			"numeric_value": -1,
		},
	}

	if !reflect.DeepEqual(result, expected) {
		t.Errorf("ExpandPaths() = %#v, expected %#v", result, expected)
	}
}
