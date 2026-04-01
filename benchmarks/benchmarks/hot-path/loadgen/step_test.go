package main

import "testing"

func TestStepCalculation(t *testing.T) {
	reqPs := 100
	rDur := 100

	step := reqPs / rDur

	if step != 1 {
		t.Errorf("Expected 1, Got: %d", step)
	}
}
