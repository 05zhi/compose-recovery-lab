package runner

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRequiredChecks(t *testing.T) {
	var checks []Check
	for _, id := range []string{"sql-documents", "database-files", "login-search-download", "external-connectivity"} {
		checks = append(checks, Check{ID: id, Required: true, Status: "passed"})
	}
	if err := validateChecks(checks); err != nil {
		t.Fatal(err)
	}
	if validateChecks(checks[:3]) == nil {
		t.Fatal("missing required check passed")
	}
	checks[1].Status = "skipped"
	if validateChecks(checks) == nil {
		t.Fatal("skipped required check passed")
	}
	checks[1].Status = "passed"
	checks[1].ID = checks[0].ID
	if validateChecks(checks) == nil {
		t.Fatal("duplicate check passed")
	}
}
func TestReportEscapesEvidence(t *testing.T) {
	r := Report{Error: "<script>alert(1)</script>", Verification: "failed", Cleanup: "complete"}
	dir := t.TempDir()
	if err := r.write(dir); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(dir, "report.html"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(data), "<script>") {
		t.Fatal("unescaped report")
	}
}
func TestRejectInvalidOwnershipJournal(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "resources.json"), []byte(`{"run_id":"production"}`), 0600)
	if _, err := LoadSession(dir); err == nil {
		t.Fatal("accepted foreign project")
	}
}
