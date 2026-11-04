// Package state persists redacted execution evidence transactionally in SQLite.
package state

import (
	"database/sql"
	"encoding/json"
	"errors"
	_ "github.com/mattn/go-sqlite3"
	"os"
	"path/filepath"
	"time"
)

type Store struct{ db *sql.DB }
type Resource struct {
	Kind string `json:"kind"`
	ID   string `json:"id"`
}
type Record struct {
	ID           string          `json:"attempt_id"`
	RunID        string          `json:"run_id"`
	Dir          string          `json:"directory"`
	Operation    string          `json:"operation"`
	Phase        string          `json:"phase"`
	ConfigHash   string          `json:"config_hash"`
	Verification string          `json:"verification_result"`
	Cleanup      string          `json:"cleanup_result"`
	Started      string          `json:"started_at"`
	Finished     string          `json:"finished_at"`
	Report       json.RawMessage `json:"report"`
}

func DefaultPath() (string, error) {
	h, e := os.UserHomeDir()
	return filepath.Join(h, ".local", "state", "compose-recovery-lab", "history.sqlite3"), e
}
func OpenDefault() (*Store, error) {
	p, e := DefaultPath()
	if e != nil {
		return nil, e
	}
	return Open(p)
}
func Open(p string) (*Store, error) {
	if e := os.MkdirAll(filepath.Dir(p), 0700); e != nil {
		return nil, e
	}
	if info, e := os.Lstat(p); e == nil && (!info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0) {
		return nil, errors.New("history must be a private regular file")
	}
	f, e := os.OpenFile(p, os.O_CREATE|os.O_RDWR, 0600)
	if e != nil {
		return nil, e
	}
	f.Close()
	db, e := sql.Open("sqlite3", p+"?_busy_timeout=5000&_foreign_keys=on&_journal_mode=WAL&_synchronous=FULL")
	if e != nil {
		return nil, e
	}
	db.SetMaxOpenConns(1)
	_, e = db.Exec(`CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(id),directory TEXT NOT NULL UNIQUE,operation TEXT NOT NULL,phase TEXT NOT NULL,config_hash TEXT NOT NULL DEFAULT '',verification TEXT NOT NULL DEFAULT 'inconclusive',cleanup TEXT NOT NULL DEFAULT 'pending',started TEXT NOT NULL,finished TEXT NOT NULL DEFAULT '',report BLOB NOT NULL DEFAULT '{}');
 CREATE TABLE IF NOT EXISTS steps(attempt_id TEXT NOT NULL REFERENCES attempts(id),name TEXT NOT NULL,status TEXT NOT NULL,started TEXT NOT NULL,finished TEXT NOT NULL DEFAULT '',PRIMARY KEY(attempt_id,name));
 CREATE TABLE IF NOT EXISTS resources(attempt_id TEXT NOT NULL REFERENCES attempts(id),kind TEXT NOT NULL,intent_key TEXT NOT NULL,external_id TEXT NOT NULL DEFAULT '',ownership_label TEXT NOT NULL,cleanup_status TEXT NOT NULL DEFAULT 'pending',PRIMARY KEY(attempt_id,kind,intent_key));
 CREATE TABLE IF NOT EXISTS check_results(attempt_id TEXT NOT NULL REFERENCES attempts(id),check_id TEXT NOT NULL,required INTEGER NOT NULL,status TEXT NOT NULL,evidence TEXT NOT NULL,PRIMARY KEY(attempt_id,check_id));
 CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,attempt_id TEXT NOT NULL REFERENCES attempts(id),timestamp TEXT NOT NULL,type TEXT NOT NULL,payload TEXT NOT NULL);
 PRAGMA user_version=1;`)
	if e != nil {
		db.Close()
		return nil, e
	}
	return &Store{db}, nil
}
func (s *Store) Close() error { return s.db.Close() }
func now() string             { return time.Now().UTC().Format(time.RFC3339Nano) }
func (s *Store) Start(id, parent, dir, operation string) (string, error) {
	tx, e := s.db.Begin()
	if e != nil {
		return "", e
	}
	defer tx.Rollback()
	root := id
	if parent != "" {
		if e = tx.QueryRow("SELECT run_id FROM attempts WHERE id=?", parent).Scan(&root); e != nil {
			return "", errors.New("retry parent is unknown")
		}
	}
	if _, e = tx.Exec("INSERT OR IGNORE INTO runs VALUES(?,?)", root, now()); e != nil {
		return "", e
	}
	if _, e = tx.Exec("INSERT INTO attempts(id,run_id,directory,operation,phase,started) VALUES(?,?,?,?,?,?)", id, root, dir, operation, "queued", now()); e != nil {
		return "", e
	}
	for _, intent := range [][2]string{{"container", "db"}, {"container", "app"}, {"network", "default"}, {"volume", "database"}, {"volume", "uploads"}} {
		if _, e = tx.Exec("INSERT INTO resources(attempt_id,kind,intent_key,ownership_label) VALUES(?,?,?,?)", id, intent[0], intent[1], id); e != nil {
			return "", e
		}
	}
	if _, e = tx.Exec("INSERT INTO events(attempt_id,timestamp,type,payload) VALUES(?,?,?,?)", id, now(), "intent", "fixed template resources recorded before Docker operations"); e != nil {
		return "", e
	}
	return root, tx.Commit()
}
func (s *Store) Phase(id, name, status string) error {
	tx, e := s.db.Begin()
	if e != nil {
		return e
	}
	defer tx.Rollback()
	if _, e = tx.Exec("UPDATE attempts SET phase=? WHERE id=?", name, id); e != nil {
		return e
	}
	finish := ""
	if status != "running" {
		finish = now()
	}
	if _, e = tx.Exec(`INSERT INTO steps VALUES(?,?,?,?,?) ON CONFLICT(attempt_id,name) DO UPDATE SET status=excluded.status,finished=excluded.finished`, id, name, status, now(), finish); e != nil {
		return e
	}
	if _, e = tx.Exec("INSERT INTO events(attempt_id,timestamp,type,payload) VALUES(?,?,?,?)", id, now(), "phase", name+":"+status); e != nil {
		return e
	}
	return tx.Commit()
}
func (s *Store) Resources(id string, resources []Resource) error {
	tx, e := s.db.Begin()
	if e != nil {
		return e
	}
	defer tx.Rollback()
	if _, e = tx.Exec("UPDATE resources SET cleanup_status='complete' WHERE attempt_id=?", id); e != nil {
		return e
	}
	for _, r := range resources {
		if _, e = tx.Exec(`INSERT INTO resources VALUES(?,?,?,?,?,'pending') ON CONFLICT(attempt_id,kind,intent_key) DO UPDATE SET cleanup_status='pending'`, id, r.Kind, "observed:"+r.ID, r.ID, id); e != nil {
			return e
		}
	}
	return tx.Commit()
}
func (s *Store) Snapshot(id string, data []byte) error {
	var r struct {
		ConfigHash   string    `json:"config_hash"`
		Verification string    `json:"verification_result"`
		Cleanup      string    `json:"cleanup_result"`
		Finished     time.Time `json:"finished_at"`
		Checks       []struct {
			ID       string `json:"id"`
			Required bool   `json:"required"`
			Status   string `json:"status"`
			Evidence string `json:"evidence"`
		} `json:"checks"`
	}
	if e := json.Unmarshal(data, &r); e != nil {
		return e
	}
	finish := ""
	if !r.Finished.IsZero() {
		finish = r.Finished.Format(time.RFC3339Nano)
	}
	tx, e := s.db.Begin()
	if e != nil {
		return e
	}
	defer tx.Rollback()
	if _, e = tx.Exec("UPDATE attempts SET config_hash=?,verification=?,cleanup=?,finished=?,report=?,phase=CASE WHEN ?<>'' THEN 'finished' ELSE phase END WHERE id=?", r.ConfigHash, r.Verification, r.Cleanup, finish, data, finish, id); e != nil {
		return e
	}
	for _, c := range r.Checks {
		if _, e = tx.Exec(`INSERT INTO check_results VALUES(?,?,?,?,?) ON CONFLICT(attempt_id,check_id) DO UPDATE SET required=excluded.required,status=excluded.status,evidence=excluded.evidence`, id, c.ID, c.Required, c.Status, c.Evidence); e != nil {
			return e
		}
	}
	return tx.Commit()
}

const columns = "id,run_id,directory,operation,phase,config_hash,verification,cleanup,started,finished,report"

func scan(row interface{ Scan(...any) error }) (Record, error) {
	var r Record
	var b []byte
	e := row.Scan(&r.ID, &r.RunID, &r.Dir, &r.Operation, &r.Phase, &r.ConfigHash, &r.Verification, &r.Cleanup, &r.Started, &r.Finished, &b)
	r.Report = b
	return r, e
}
func (s *Store) Get(id string, exact bool) (Record, error) {
	if exact {
		return scan(s.db.QueryRow("SELECT "+columns+" FROM attempts WHERE id=?", id))
	}
	return scan(s.db.QueryRow("SELECT "+columns+" FROM attempts WHERE run_id=COALESCE((SELECT run_id FROM attempts WHERE id=?),?) ORDER BY started DESC LIMIT 1", id, id))
}
func (s *Store) List(limit int, pending bool) ([]Record, error) {
	if limit < 1 || limit > 1000 {
		return nil, errors.New("history limit must be 1..1000")
	}
	filter := ""
	if pending {
		filter = " WHERE finished='' OR cleanup<>'complete'"
	}
	rows, e := s.db.Query("SELECT "+columns+" FROM attempts"+filter+" ORDER BY started DESC LIMIT ?", limit)
	if e != nil {
		return nil, e
	}
	defer rows.Close()
	result := []Record{}
	for rows.Next() {
		r, e := scan(rows)
		if e != nil {
			return nil, e
		}
		result = append(result, r)
	}
	return result, rows.Err()
}
