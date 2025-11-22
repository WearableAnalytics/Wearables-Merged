package wplug

import (
	"log"
	"path"
	"reflect"
	"testing"
)

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
