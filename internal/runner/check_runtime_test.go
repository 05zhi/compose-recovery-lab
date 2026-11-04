package runner

import (
	"github.com/05zhi/compose-recovery-lab/internal/checks"
	"testing"
)

func TestAggregate(t *testing.T) {
	specs := []checks.Spec{{ID: "required", Required: true}, {ID: "optional"}}
	for _, tc := range []struct {
		rows []Check
		want string
	}{
		{[]Check{{ID: "required", Required: true, Status: "passed"}}, "passed"},
		{[]Check{{ID: "required", Required: true, Status: "skipped"}}, "inconclusive"},
		{[]Check{{ID: "required", Required: true, Status: "error"}, {ID: "optional", Status: "failed"}}, "failed"},
		{[]Check{{ID: "required", Required: true, Status: "passed"}, {ID: "required", Required: true, Status: "passed"}}, "inconclusive"},
	} {
		got, _ := Aggregate(specs, tc.rows)
		if got != tc.want {
			t.Fatalf("%s != %s", got, tc.want)
		}
	}
}
