package runner

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/05zhi/compose-recovery-lab/internal/state"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

const label = "io.compose-recovery-lab.run"

type Images struct {
	Postgres string `json:"postgres"`
	App      string `json:"app"`
}
type Resource struct {
	Kind string `json:"kind"`
	ID   string `json:"id"`
}
type Session struct {
	ID        string     `json:"run_id"`
	Dir       string     `json:"-"`
	Resources []Resource `json:"resources"`
	Images    Images     `json:"images"`
	password  string
	store     *state.Store
	logicalID string
}

func randomID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}

// Docker stderr can contain connection strings and environment values. The CLI
// stores only the operation and exit condition; checks emit bounded synthetic evidence.
func docker(ctx context.Context, input io.Reader, output io.Writer, args ...string) error {
	step, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()
	cmd := exec.CommandContext(step, "docker", args...)
	cmd.Stdin = input
	cmd.Stdout = output
	cmd.Stderr = io.Discard
	// Explicit local daemon: do not inherit remote contexts, Compose overrides or TLS settings.
	cmd.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + os.Getenv("HOME"), "DOCKER_HOST=unix:///var/run/docker.sock"}
	if err := cmd.Run(); err != nil {
		if step.Err() != nil {
			return step.Err()
		}
		return fmt.Errorf("docker %s failed (diagnostic output suppressed)", args[0])
	}
	return nil
}
func capture(ctx context.Context, args ...string) (string, error) {
	var b bytes.Buffer
	err := docker(ctx, nil, &b, args...)
	return strings.TrimSpace(b.String()), err
}
func writeJSON(name string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	tmp := name + ".tmp"
	if err = os.WriteFile(tmp, append(b, '\n'), 0600); err != nil {
		return err
	}
	return os.Rename(tmp, name)
}

func NewSession(root string, images Images) (*Session, error) {
	if err := os.MkdirAll(root, 0700); err != nil {
		return nil, err
	}
	dir, err := os.MkdirTemp(root, "crl-")
	if err != nil {
		return nil, err
	}
	s := &Session{ID: "crl-" + randomID(), Dir: dir, Images: images, password: randomID()}
	// Persist intent before any Docker side effect. Discovery reconciles resources by labels.
	if err = s.save(); err != nil {
		return nil, err
	}
	return s, nil
}
func (s *Session) save() error {
	if err := writeJSON(filepath.Join(s.Dir, "resources.json"), s); err != nil {
		return err
	}
	if s.store != nil {
		rs := []state.Resource{}
		for _, r := range s.Resources {
			rs = append(rs, state.Resource{Kind: r.Kind, ID: r.ID})
		}
		return s.store.Resources(s.ID, rs)
	}
	return nil
}

func LoadSession(dir string) (*Session, error) {
	data, err := os.ReadFile(filepath.Join(dir, "resources.json"))
	if err != nil {
		return nil, err
	}
	var s Session
	if err = json.Unmarshal(data, &s); err != nil {
		return nil, err
	}
	if !regexp.MustCompile(`^crl-[0-9a-f]{32}$`).MatchString(s.ID) {
		return nil, errors.New("invalid ownership journal")
	}
	s.Dir = dir
	return &s, nil
}

func (s *Session) prepare(ctx context.Context) error {
	for _, image := range []string{s.Images.Postgres, s.Images.App} {
		if !regexp.MustCompile(`^(postgres@)?sha256:[0-9a-f]{64}$`).MatchString(image) {
			return errors.New("immutable image reference required")
		}
		if _, err := capture(ctx, "image", "inspect", image); err != nil {
			return errors.New("required image unavailable locally; prepare images before running")
		}
	}
	labels := map[string]string{label: s.ID}
	common := func(image string) map[string]any {
		return map[string]any{"image": image, "pull_policy": "never", "labels": labels, "mem_limit": "512m", "cpus": 1, "pids_limit": 128, "security_opt": []string{"no-new-privileges:true"}}
	}
	db := common(s.Images.Postgres)
	db["environment"] = map[string]string{"POSTGRES_USER": "bootstrap", "POSTGRES_DB": "postgres", "POSTGRES_PASSWORD": s.password}
	db["volumes"] = []string{"database:/var/lib/postgresql/data"}
	db["healthcheck"] = map[string]any{"test": []string{"CMD", "pg_isready", "-U", "bootstrap", "-d", "postgres"}, "interval": "1s", "timeout": "3s", "retries": 60}
	app := common(s.Images.App)
	app["environment"] = map[string]string{"DATABASE_URL": "postgresql://demo:" + s.password + "@db/documents", "DEMO_PASSWORD": s.password}
	app["volumes"] = []string{"uploads:/uploads"}
	app["read_only"] = true
	app["cap_drop"] = []string{"ALL"}
	spec := map[string]any{"services": map[string]any{"db": db, "app": app}, "networks": map[string]any{"default": map[string]any{"internal": true, "labels": labels}}, "volumes": map[string]any{"database": map[string]any{"labels": labels}, "uploads": map[string]any{"labels": labels}}}
	return writeJSON(filepath.Join(s.Dir, "compose.json"), spec)
}
func (s *Session) compose(ctx context.Context, args ...string) error {
	base := []string{"compose", "-p", s.ID, "-f", filepath.Join(s.Dir, "compose.json")}
	err := docker(ctx, nil, io.Discard, append(base, args...)...)
	// Always reconcile, including partial compose failures.
	reconciliation, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	return errors.Join(err, s.discover(reconciliation))
}
func (s *Session) container(ctx context.Context, service string) (string, error) {
	ids, err := capture(ctx, "ps", "-aq", "--filter", "label="+label+"="+s.ID, "--filter", "label=com.docker.compose.service="+service)
	if err != nil {
		return "", err
	}
	parts := strings.Fields(ids)
	if len(parts) != 1 {
		return "", errors.New("expected exactly one owned service")
	}
	return parts[0], nil
}
func (s *Session) discover(ctx context.Context) error {
	var resources []Resource
	for _, kind := range []string{"container", "network", "volume"} {
		args := []string{kind, "ls", "-q", "--filter", "label=" + label + "=" + s.ID}
		if kind == "container" {
			args = []string{"ps", "-aq", "--no-trunc", "--filter", "label=" + label + "=" + s.ID}
		}
		if kind == "network" {
			args = append(args, "--no-trunc")
		}
		ids, err := capture(ctx, args...)
		if err != nil {
			return err
		}
		for _, id := range strings.Fields(ids) {
			if err = s.owned(ctx, kind, id); err != nil {
				return err
			}
			resources = append(resources, Resource{kind, id})
		}
	}
	s.Resources = resources
	return s.save()
}
func (s *Session) owned(ctx context.Context, kind, id string) error {
	raw, err := capture(ctx, kind, "inspect", id)
	if err != nil {
		return err
	}
	var rows []struct {
		ID     string
		Name   string
		Labels map[string]string
		Config struct{ Labels map[string]string }
	}
	if err = json.Unmarshal([]byte(raw), &rows); err != nil || len(rows) != 1 {
		return errors.New("invalid resource inspection")
	}
	row := rows[0]
	labels := row.Labels
	if kind == "container" {
		labels = row.Config.Labels
	}
	actual := row.ID
	if kind == "volume" {
		actual = row.Name
	}
	if actual != id || labels[label] != s.ID || labels["com.docker.compose.project"] != s.ID {
		return errors.New("resource ownership mismatch; refusing deletion")
	}
	return nil
}
func (s *Session) Cleanup(ctx context.Context) error {
	if err := s.discover(ctx); err != nil {
		return err
	}
	var failures []error
	for _, r := range s.Resources {
		if err := s.owned(ctx, r.Kind, r.ID); err != nil {
			failures = append(failures, err)
			continue
		}
		args := []string{r.Kind, "rm", r.ID}
		if r.Kind == "container" {
			args = []string{"container", "rm", "-f", r.ID}
		}
		if err := docker(ctx, nil, io.Discard, args...); err != nil {
			failures = append(failures, err)
		}
	}
	if err := s.discover(ctx); err != nil {
		failures = append(failures, err)
	}
	if len(s.Resources) > 0 {
		failures = append(failures, errors.New("owned resources remain"))
	}
	if len(failures) == 0 {
		if err := os.Remove(filepath.Join(s.Dir, "compose.json")); err != nil && !os.IsNotExist(err) {
			failures = append(failures, err)
		}
	}
	return errors.Join(failures...)
}
func wait(ctx context.Context, probe func() error) error {
	deadline, cancel := context.WithTimeout(ctx, 60*time.Second)
	defer cancel()
	for {
		if err := probe(); err == nil {
			return nil
		}
		select {
		case <-deadline.Done():
			return errors.New("service readiness timeout")
		case <-time.After(300 * time.Millisecond):
		}
	}
}
func (s *Session) startDB(ctx context.Context) error {
	if err := s.compose(ctx, "up", "-d", "--wait", "db"); err != nil {
		return err
	}
	id, err := s.container(ctx, "db")
	if err != nil {
		return err
	}
	sql := "CREATE ROLE demo LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '" + s.password + "'; CREATE DATABASE documents OWNER demo;"
	return docker(ctx, strings.NewReader(sql), io.Discard, "exec", "-i", id, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "bootstrap", "-d", "postgres")
}
func (s *Session) startApp(ctx context.Context) error {
	if err := s.compose(ctx, "up", "-d", "app"); err != nil {
		return err
	}
	id, err := s.container(ctx, "app")
	if err != nil {
		return err
	}
	return wait(ctx, func() error {
		return docker(ctx, nil, io.Discard, "exec", id, "python", "-c", `import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)`)
	})
}
