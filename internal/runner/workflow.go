package runner

import (
	"archive/tar"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"html/template"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"github.com/05zhi/compose-recovery-lab/internal/source"
	"github.com/05zhi/compose-recovery-lab/internal/state"
)

type Check struct {
	ID       string `json:"id"`
	Required bool   `json:"required"`
	Status   string `json:"status"`
	Evidence string `json:"evidence"`
}
type Step struct {
	Name    string    `json:"name"`
	Started time.Time `json:"started_at"`
	Seconds float64   `json:"seconds"`
	Status  string    `json:"status"`
}
type Report struct {
	LogicalRunID string `json:"logical_run_id"`
	AttemptID    string `json:"attempt_id"`
	Phase        string `json:"phase"`
	store        *state.Store
	dir          string
	ConfigHash   string           `json:"config_hash,omitempty"`
	RunID        string           `json:"run_id"`
	Operation    string           `json:"operation"`
	Started      time.Time        `json:"started_at"`
	Finished     time.Time        `json:"finished_at"`
	Verification string           `json:"verification_result"`
	Cleanup      string           `json:"cleanup_result"`
	BackupID     string           `json:"backup_id,omitempty"`
	Backup       *source.Manifest `json:"backup,omitempty"`
	Images       Images           `json:"images"`
	Steps        []Step           `json:"steps"`
	Checks       []Check          `json:"checks"`
	Remaining    []Resource       `json:"remaining_resources"`
	Error        string           `json:"error,omitempty"`
	Limitations  []string         `json:"limitations"`
}

func (r *Report) step(name string, fn func() error) error {
	start := time.Now().UTC()
	r.Phase = name
	if r.store != nil {
		if err := r.store.Phase(r.RunID, name, "running"); err != nil {
			return err
		}
		if err := r.write(r.dir); err != nil {
			return err
		}
	}
	fmt.Fprintln(os.Stderr, name)
	err := fn()
	status := "passed"
	if err != nil {
		status = "error"
	}
	r.Steps = append(r.Steps, Step{name, start, time.Since(start).Seconds(), status})
	if r.store != nil {
		err = errors.Join(err, r.store.Phase(r.RunID, name, status), r.write(r.dir))
	}
	return err
}

func (r *Report) write(dir string) error {
	if r.store != nil {
		b, e := json.Marshal(r)
		if e != nil {
			return e
		}
		if e = r.store.Snapshot(r.RunID, b); e != nil {
			return e
		}
	}
	if err := writeJSON(filepath.Join(dir, "report.json"), r); err != nil {
		return err
	}
	t := template.Must(template.New("report").Parse(`<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><title>Compose Recovery Lab</title><style>body{font:16px system-ui;max-width:960px;margin:40px auto;padding:0 20px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ccc;text-align:left}code{overflow-wrap:anywhere}</style><h1>Compose Recovery Lab</h1><p>Run <code>{{.RunID}}</code></p><p>Verification: <b>{{.Verification}}</b> · Cleanup: <b>{{.Cleanup}}</b></p><p>{{.Error}}</p><p>Backup: <code>{{.BackupID}}</code></p><p>PostgreSQL image: <code>{{.Images.Postgres}}</code></p><p>Application image: <code>{{.Images.App}}</code></p><p>{{.Started}} — {{.Finished}}</p>{{with .Backup}}<p>Consistency: {{.Consistency}}</p><p>Backup interval: {{.StartedAt}} — {{.FinishedAt}}; attachments: {{.AttachmentCount}}</p>{{end}}<h2>Checks</h2><table>{{range .Checks}}<tr><th>{{.ID}}</th><td>{{.Status}}</td><td>{{.Evidence}}</td></tr>{{end}}</table><h2>Phases</h2><table>{{range .Steps}}<tr><th>{{.Name}}</th><td>{{.Status}}</td><td>{{printf "%.3f" .Seconds}} s</td></tr>{{end}}</table><h2>Coverage and limitations</h2><ul>{{range .Limitations}}<li>{{.}}</li>{{end}}</ul></html>`))
	f, err := os.OpenFile(filepath.Join(dir, "report.html"), os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	return errors.Join(t.Execute(f, r), f.Close())
}

// Lock serializes this Linux user's drills even when different output roots are used.
func Lock() (*os.File, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, err
	}
	dir := filepath.Join(home, ".local", "state", "compose-recovery-lab")
	if err = os.MkdirAll(dir, 0700); err != nil {
		return nil, err
	}
	f, err := os.OpenFile(filepath.Join(dir, "runner.lock"), os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, err
	}
	if err = syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		return nil, errors.New("another drill is active for this account")
	}
	return f, nil
}
func freeSpace(dir string) error {
	var st syscall.Statfs_t
	if err := syscall.Statfs(dir, &st); err != nil {
		return err
	}
	if st.Bavail*uint64(st.Bsize) < 1<<30 {
		return errors.New("less than 1 GiB free workspace space")
	}
	return nil
}

func execute(ctx context.Context, root, operation string, images Images, fn func(context.Context, *Session, *Report) error) (dir string, err error) {
	s, err := NewSession(root, images)
	if err != nil {
		return "", err
	}
	dir = s.Dir
	s.store, err = state.OpenDefault()
	if err != nil {
		return dir, err
	}
	defer s.store.Close()
	parent, _ := ctx.Value(retryKey{}).(string)
	s.logicalID, err = s.store.Start(s.ID, parent, s.Dir, operation)
	if err != nil {
		return dir, err
	}
	r := &Report{RunID: s.ID, Operation: operation, Started: time.Now().UTC(), Verification: "inconclusive", Cleanup: "pending", Images: images, Checks: []Check{}, Limitations: []string{"M1 synthetic document-app-v1 only; not an arbitrary Compose runner", "Required coverage: all 10 fixture attachments; see individual check status for executed coverage", "Demo account password replaced with a generated drill password; owner/ACL excluded during restore", "External connectivity check covers one TCP endpoint only; not a hostile-code sandbox", "Image download/build excluded from timing; local cached images required", "SQLite attempts retain previous evidence; retry always restores into fresh resources"}}
	r.ConfigHash, _ = ctx.Value(configHashKey{}).(string)
	r.store = s.store
	r.dir = dir
	r.LogicalRunID = s.logicalID
	r.AttemptID = s.ID
	r.Phase = "queued"
	if operation == "run" {
		for _, id := range []string{"sql-documents", "database-files", "login-search-download", "external-connectivity"} {
			r.Checks = append(r.Checks, Check{id, true, "skipped", "verification phase not reached"})
		}
	}
	// Establish a durable initial report for manual cleanup after an uncatchable crash.
	if err = r.write(dir); err != nil {
		return dir, err
	}
	defer func() {
		if ctx.Err() != nil && r.Verification != "failed" {
			r.Verification = "canceled"
		}
		if err != nil {
			r.Error = err.Error()
		}
		cleanupCtx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		defer cancel()
		cleanupErr := r.step("cleaning", func() error { return s.Cleanup(cleanupCtx) })
		r.Cleanup = "complete"
		if cleanupErr != nil {
			r.Cleanup = "failed"
		}
		r.Remaining = s.Resources
		r.Finished = time.Now().UTC()
		r.Phase = "finished"
		// Only the private staging child created by this run is removed, never a source path.
		stageErr := os.RemoveAll(filepath.Join(dir, "staged"))
		if stageErr != nil {
			r.Cleanup = "failed"
		}
		err = errors.Join(err, cleanupErr, stageErr)
		if err != nil {
			r.Error = err.Error()
		}
		err = errors.Join(err, r.write(dir))
	}()
	if err = r.step("preflight", func() error {
		if err := freeSpace(dir); err != nil {
			return err
		}
		return s.prepare(ctx)
	}); err != nil {
		return dir, err
	}
	monitored, cancel := context.WithCancel(ctx)
	defer cancel()
	go func() {
		ticker := time.NewTicker(time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-monitored.Done():
				return
			case <-ticker.C:
				if freeSpace(dir) != nil {
					cancel()
					return
				}
			}
		}
	}()
	err = fn(monitored, s, r)
	if err == nil {
		r.Verification = "passed"
	}
	return dir, err
}

type limitWriter struct {
	w io.Writer
	n int64
}

func (w *limitWriter) Write(b []byte) (int, error) {
	if int64(len(b)) > w.n {
		return 0, errors.New("artifact size limit exceeded")
	}
	n, err := w.w.Write(b)
	w.n -= int64(n)
	return n, err
}
func toFile(ctx context.Context, name string, args ...string) error {
	f, err := os.OpenFile(name, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	err = docker(ctx, nil, &limitWriter{f, source.MaxFileSize}, args...)
	return errors.Join(err, f.Close())
}

func normalizeTar(input, output, omit string) (int, error) {
	in, err := os.Open(input)
	if err != nil {
		return 0, err
	}
	defer in.Close()
	out, err := os.OpenFile(output, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return 0, err
	}
	tr := tar.NewReader(in)
	tw := tar.NewWriter(out)
	count := 0
	for {
		h, e := tr.Next()
		if e == io.EOF {
			break
		}
		if e != nil {
			err = e
			break
		}
		name := strings.TrimPrefix(strings.TrimSuffix(h.Name, "/"), "./")
		if name == "." || name == "" {
			continue
		}
		if name == omit {
			continue
		}
		if !source.SafeName(name) || (h.Typeflag != tar.TypeReg && h.Typeflag != tar.TypeDir) {
			err = errors.New("unsafe source attachment archive")
			break
		}
		h.Name = name
		h.Uid = 10001
		h.Gid = 10001
		h.Uname = ""
		h.Gname = ""
		h.PAXRecords = nil
		if h.Typeflag == tar.TypeDir {
			h.Mode = 0755
		} else {
			h.Mode = 0644
			count++
		}
		if err = tw.WriteHeader(h); err != nil {
			break
		}
		if _, err = io.Copy(tw, tr); err != nil {
			break
		}
	}
	err = errors.Join(err, tw.Close(), out.Close())
	if err == nil {
		_, err = source.ValidateTar(output)
	}
	return count, err
}

func Backup(ctx context.Context, root, out string, images Images, omit bool) (string, error) {
	out, err := filepath.Abs(out)
	if err != nil {
		return "", err
	}
	if _, err = os.Lstat(out); !os.IsNotExist(err) {
		return "", errors.New("backup destination must not exist")
	}
	if err = os.MkdirAll(filepath.Dir(out), 0700); err != nil {
		return "", err
	}
	partial := out + ".partial"
	if err = os.Mkdir(partial, 0700); err != nil {
		return "", err
	}
	return execute(ctx, root, "backup", images, func(ctx context.Context, s *Session, r *Report) error {
		if err := r.step("seeding", func() error {
			if err := s.startDB(ctx); err != nil {
				return err
			}
			if err := s.compose(ctx, "run", "--rm", "--no-deps", "app", "python", "app.py", "seed"); err != nil {
				return err
			}
			return s.startApp(ctx)
		}); err != nil {
			return err
		}
		app, err := s.container(ctx, "app")
		if err != nil {
			return err
		}
		db, err := s.container(ctx, "db")
		if err != nil {
			return err
		}
		if err = r.step("source-smoke", func() error { return docker(ctx, nil, io.Discard, "exec", app, "python", "smoke.py") }); err != nil {
			return err
		}
		return r.step("backup", func() (backupErr error) {
			started := time.Now().UTC()
			// Always resume the source, including dump/tar/publish failure, before cleanup.
			defer func() {
				resume, cancel := context.WithTimeout(context.Background(), 30*time.Second)
				defer cancel()
				backupErr = errors.Join(backupErr, s.compose(resume, "start", "app"))
			}()
			if err := s.compose(ctx, "stop", "--timeout", "10", "app"); err != nil {
				return err
			}
			if err := toFile(ctx, filepath.Join(partial, "database.dump"), "exec", db, "pg_dump", "-U", "demo", "-d", "documents", "--format=custom", "--no-owner", "--no-acl"); err != nil {
				return err
			}
			raw := filepath.Join(s.Dir, "uploads.raw.tar")
			if err := toFile(ctx, raw, "cp", app+":/uploads/.", "-"); err != nil {
				return err
			}
			omitName := ""
			if omit {
				omitName = "document-01.txt"
			}
			count, err := normalizeTar(raw, filepath.Join(partial, "uploads.tar"), omitName)
			os.Remove(raw)
			if err != nil {
				return err
			}
			if err = os.WriteFile(filepath.Join(partial, "app-config.sanitized.json"), []byte("{\"app\":\"document-app-v1\",\"read_only_api\":true}\n"), 0600); err != nil {
				return err
			}
			m := source.Manifest{SchemaVersion: 1, BackupID: "backup-" + randomID(), AppVersion: "document-app-v1", PostgresMajor: 17, PostgresImage: images.Postgres, AppImage: images.App, Extensions: []string{"plpgsql"}, StartedAt: started, FinishedAt: time.Now().UTC(), AttachmentCount: count, Consistency: "read-only fixture API stopped during pg_dump and attachment capture", Limitations: []string{"synthetic data only; no external writers; original owner/ACL excluded"}}
			if omit {
				m.Limitations = append(m.Limitations, "fault injection: document-01.txt intentionally omitted")
			}
			if err = source.WriteManifest(partial, m); err != nil {
				return err
			}
			if err = os.Rename(partial, out); err != nil {
				return err
			}
			published, err := source.Load(out)
			if err != nil {
				return err
			}
			r.BackupID = m.BackupID
			r.Backup = &published
			return nil
		})
	})
}

func Run(ctx context.Context, root, bundle string, images Images) (string, error) {
	return runBundle(ctx, root, bundle, images, "", "")
}
func RunConfigured(ctx context.Context, root, bundle string, images Images, configHash, manifestHash string) (string, error) {
	return runBundle(context.WithValue(ctx, configHashKey{}, configHash), root, bundle, images, configHash, manifestHash)
}
func runBundle(ctx context.Context, root, bundle string, images Images, configHash, manifestHash string) (string, error) {
	return execute(ctx, root, "run", images, func(ctx context.Context, s *Session, r *Report) error {
		r.ConfigHash = configHash
		staged := filepath.Join(s.Dir, "staged")
		var m source.Manifest
		if err := r.step("staging", func() error { var err error; m, err = source.Stage(bundle, staged); return err }); err != nil {
			r.Verification = "failed"
			return err
		}
		if manifestHash != "" {
			digest, err := source.Digest(filepath.Join(staged, "manifest.json"))
			if err != nil || digest.SHA256 != manifestHash {
				r.Verification = "failed"
				return errors.New("manifest changed after planning; create a fresh plan")
			}
		}
		if m.AppImage != images.App || m.PostgresImage != images.Postgres {
			r.Verification = "failed"
			return errors.New("backup images do not match the trusted local image lock")
		}
		r.BackupID = m.BackupID
		r.Backup = &m
		if err := r.step("restoring", func() error {
			if err := s.startDB(ctx); err != nil {
				return err
			}
			db, err := s.container(ctx, "db")
			if err != nil {
				return err
			}
			dump, err := os.Open(filepath.Join(staged, "database.dump"))
			if err != nil {
				return err
			}
			err = docker(ctx, dump, io.Discard, "exec", "-i", db, "pg_restore", "-U", "demo", "-d", "documents", "--no-owner", "--no-acl", "--exit-on-error", "--single-transaction")
			dump.Close()
			if err != nil {
				return err
			}
			if err = s.compose(ctx, "create", "app"); err != nil {
				return err
			}
			app, err := s.container(ctx, "app")
			if err != nil {
				return err
			}
			uploads, err := os.Open(filepath.Join(staged, "uploads.tar"))
			if err != nil {
				return err
			}
			err = docker(ctx, uploads, io.Discard, "cp", "--archive", "-", app+":/uploads")
			uploads.Close()
			if err != nil {
				return err
			}
			return nil
		}); err != nil {
			return err
		}
		if err := r.step("starting", func() error {
			if err := s.startApp(ctx); err != nil {
				return err
			}
			app, err := s.container(ctx, "app")
			if err != nil {
				return err
			}
			return docker(ctx, nil, io.Discard, "exec", app, "python", "app.py", "reset-password")
		}); err != nil {
			return err
		}
		return r.step("verifying", func() error {
			app, err := s.container(ctx, "app")
			if err != nil {
				return err
			}
			raw, err := capture(ctx, "exec", app, "python", "probe.py")
			if err != nil {
				return err
			}
			if err = json.Unmarshal([]byte(raw), &r.Checks); err != nil {
				return errors.New("invalid probe evidence")
			}
			if err = validateChecks(r.Checks); err != nil {
				r.Verification = "failed"
				return err
			}
			return nil
		})
	})
}
func validateChecks(checks []Check) error {
	expected := map[string]bool{"sql-documents": false, "database-files": false, "login-search-download": false, "external-connectivity": false}
	for _, c := range checks {
		done, ok := expected[c.ID]
		if !ok || done || !c.Required || c.Status != "passed" {
			return errors.New("required check failed, skipped, duplicated or unexpected")
		}
		expected[c.ID] = true
	}
	for _, done := range expected {
		if !done {
			return errors.New("required check missing")
		}
	}
	return nil
}

// RecoverCleanup does not resume a partially restored DB or convert an interrupted run to passed.
func RecoverCleanup(ctx context.Context, dir string) error {
	s, err := LoadSession(dir)
	if err != nil {
		return err
	}
	s.store, err = state.OpenDefault()
	if err != nil {
		return err
	}
	defer s.store.Close()
	if _, e := s.store.Get(s.ID, true); e != nil {
		if _, e = s.store.Start(s.ID, "", s.Dir, "recovered"); e != nil {
			return e
		}
	}
	err = s.Cleanup(ctx)
	data, readErr := os.ReadFile(filepath.Join(dir, "report.json"))
	if readErr != nil {
		record, e := s.store.Get(s.ID, true)
		if e != nil {
			return errors.Join(err, e)
		}
		data = record.Report
	}
	var r Report
	if e := json.Unmarshal(data, &r); e != nil {
		return errors.Join(err, e)
	}
	if r.RunID == "" {
		r.RunID = s.ID
		r.Verification = "inconclusive"
	}
	r.store = s.store
	r.dir = dir
	r.AttemptID = s.ID
	r.Cleanup = "complete"
	if err != nil {
		r.Cleanup = "failed"
	}
	r.Remaining = s.Resources
	if err == nil && r.Verification == "passed" {
		r.Error = ""
	}
	if r.Finished.IsZero() {
		if r.Verification != "failed" {
			r.Verification = "inconclusive"
		}
		r.Error = "interrupted execution; cleanup only, no verification resumed"
		r.Finished = time.Now().UTC()
		r.Phase = "finished"
	}
	stageErr := os.RemoveAll(filepath.Join(dir, "staged"))
	if stageErr != nil {
		r.Cleanup = "failed"
	}
	return errors.Join(err, stageErr, r.write(dir))
}

type configHashKey struct{}
type retryKey struct{}

func RetryContext(ctx context.Context, parent string) context.Context {
	return context.WithValue(ctx, retryKey{}, parent)
}

// Reconcile is called while the account-wide execution lock is held.
func Reconcile(ctx context.Context) error {
	db, err := state.OpenDefault()
	if err != nil {
		return err
	}
	items, err := db.List(1000, true)
	db.Close()
	if err != nil {
		return err
	}
	for _, item := range items {
		if err = RecoverCleanup(ctx, item.Dir); err != nil {
			return errors.New("prior attempt cleanup failed; new run blocked")
		}
	}
	return nil
}
