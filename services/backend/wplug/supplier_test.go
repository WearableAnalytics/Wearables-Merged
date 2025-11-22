package wplug

import (
	"log"
	"path"
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

func TestGenerateBaseJSON(t *testing.T) {
	// First generate a Schema Map
	p := path.Join("test-resources", "test1-schema.json")

	schema, err := BuildSchema(p)
	if err != nil {
		t.Errorf("unexpected error building schema: %v", err)
	}

	base := GenerateBaseJSON(schema)
	log.Printf("%v", base)

}
