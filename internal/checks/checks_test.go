package checks

import (
	"testing"
)

func TestBoundary(t *testing.T) {
	for _, s := range []Spec{{ID: "x", Type: "sql", Query: "DELETE FROM documents"}, {ID: "x", Type: "file", Root: "uploads", Path: "../secret"}, {ID: "x", Type: "http", Path: "//example.org"}, {ID: "x", Type: "http", Path: "http://production"}} {
		if Validate([]Spec{s}) == nil {
			t.Fatal("unsafe check accepted", s.Type)
		}
	}
	if Validate([]Spec{{ID: "x", Type: "sql", Query: "SELECT count(*) FROM documents"}}) != nil {
		t.Fatal("valid SELECT rejected")
	}
	if Validate([]Spec{{ID: "x"}, {ID: "x"}}) == nil {
		t.Fatal("duplicate IDs accepted")
	}
}
