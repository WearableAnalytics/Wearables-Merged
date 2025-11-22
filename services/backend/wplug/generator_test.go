package wplug

import "testing"

func TestNewSimpleNumericGenerator(t *testing.T) {
	base := 1000.0
	amp := 100.0

	sng := NewSimpleNumericGenerator(base, amp)

	if sng.Base != 1000.0 {
		t.Errorf("wow")
	}

	if sng.Amp != 100.0 {
		t.Errorf("wow")
	}
}
