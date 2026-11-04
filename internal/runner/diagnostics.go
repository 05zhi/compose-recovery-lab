package runner

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Diagnostics retains only explicit safe log categories and container state.
// Raw SQL, paths, exception text, credentials and arbitrary application output never persist.
func safeLogLines(raw string) []string {
	out := []string{}
	for _, line := range strings.Split(strings.TrimSpace(raw), "\n") {
		if line == "" {
			continue
		}
		message := "[redacted service log line]"
		for _, allowed := range []string{"database system is ready to accept connections", "database system is shut down", "database system was interrupted", "database system is starting up", "Traceback (most recent call last):"} {
			if strings.Contains(line, allowed) {
				message = allowed
				break
			}
		}
		out = append(out, message)
	}
	return out
}
func (s *Session) diagnostics(ctx context.Context) error {
	type service struct {
		Service   string   `json:"service"`
		Status    string   `json:"status"`
		ExitCode  int      `json:"exit_code"`
		OOMKilled bool     `json:"oom_killed"`
		Logs      []string `json:"redacted_log_lines"`
	}
	items := []service{}
	for _, name := range []string{"db", "app"} {
		id, err := s.container(ctx, name)
		if err != nil {
			continue
		}
		if s.owned(ctx, "container", id) != nil {
			continue
		}
		raw, err := capture(ctx, "inspect", "--format", "{{json .State}}", id)
		if err != nil {
			continue
		}
		var state struct {
			Status    string
			ExitCode  int
			OOMKilled bool
		}
		if json.Unmarshal([]byte(raw), &state) != nil {
			continue
		}
		var output bytes.Buffer
		bounded := &limitWriter{&output, 65536}
		cmd := exec.CommandContext(ctx, "docker", "logs", "--tail", "50", id)
		cmd.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + os.Getenv("HOME"), "DOCKER_HOST=unix:///var/run/docker.sock"}
		cmd.Stdout = bounded
		cmd.Stderr = bounded
		_ = cmd.Run()
		items = append(items, service{name, state.Status, state.ExitCode, state.OOMKilled, safeLogLines(output.String())})
	}
	return writeJSON(filepath.Join(s.Dir, "diagnostics.json"), items)
}
