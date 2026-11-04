package state

import (
	"encoding/json"
	"path/filepath"
	"testing"
)

func TestDurableAttemptsAndResources(t *testing.T) {
	path := filepath.Join(t.TempDir(), "history.sqlite3")
	s, e := Open(path)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = s.Start("one", "", "/private/one", "run"); e != nil {
		t.Fatal(e)
	}
	if e = s.Phase("one", "restoring", "running"); e != nil {
		t.Fatal(e)
	}
	if e = s.Resources("one", []Resource{{"volume", "owned"}}); e != nil {
		t.Fatal(e)
	}
	if e = s.Snapshot("one", []byte(`{"verification_result":"inconclusive","cleanup_result":"pending"}`)); e != nil {
		t.Fatal(e)
	}
	s.Close()
	s, e = Open(path)
	if e != nil {
		t.Fatal(e)
	}
	defer s.Close()
	r, e := s.Get("one", true)
	if e != nil || r.Phase != "restoring" {
		t.Fatal(r, e)
	}
	if _, e = s.Start("two", "one", "/private/two", "run"); e != nil {
		t.Fatal(e)
	}
	r, e = s.Get("one", false)
	if e != nil || r.ID != "two" || r.RunID != "one" {
		t.Fatal(r, e)
	}
	if e = s.Resources("one", nil); e != nil {
		t.Fatal(e)
	}
	var count int
	s.db.QueryRow("SELECT count(*) FROM resources WHERE external_id='owned' AND cleanup_status='complete'").Scan(&count)
	if count != 1 {
		t.Fatal("resource identity lost")
	}
	records, e := s.List(10, true)
	if e != nil || len(records) != 2 {
		t.Fatal(records, e)
	}
	if _, e = json.Marshal(records); e != nil {
		t.Fatal(e)
	}
}
