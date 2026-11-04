// Package doctor checks readiness without creating directories or Docker resources.
package doctor

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/05zhi/compose-recovery-lab/internal/planner"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"
)

type Check struct {
	ID     string `json:"id"`
	Status string `json:"status"`
	Detail string `json:"detail"`
}
type Report struct {
	Status     string  `json:"status"`
	Ready      bool    `json:"ready"`
	ConfigHash string  `json:"config_hash"`
	BackupID   string  `json:"backup_id"`
	Checks     []Check `json:"checks"`
}

func probe(ctx context.Context, out any, args ...string) error {
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "docker", args...)
	cmd.Env = []string{"PATH=" + os.Getenv("PATH"), "HOME=" + os.Getenv("HOME"), "DOCKER_HOST=unix:///var/run/docker.sock"}
	data, err := cmd.Output()
	if err != nil {
		return fmt.Errorf("local Docker query failed")
	}
	if len(data) > 1<<20 {
		return fmt.Errorf("Docker response exceeds limit")
	}
	return json.Unmarshal(data, out)
}
func CheckPlan(ctx context.Context, p planner.Plan, offline bool) Report {
	r := Report{Status: "ready", Ready: true, ConfigHash: p.ConfigHash, BackupID: p.BackupID, Checks: []Check{{"config-manifest-mapping", "passed", "schema, hashes, archive bounds, mappings and image lock agree"}}}
	add := func(id string, ok bool, detail string) {
		status := "passed"
		if !ok {
			status = "failed"
			r.Ready = false
			r.Status = "not_ready"
		}
		r.Checks = append(r.Checks, Check{id, status, detail})
	}
	if offline {
		r.Status = "offline_valid"
		r.Ready = false
		r.Checks = append(r.Checks, Check{"runtime", "skipped", "explicit offline mode; Docker and free space not checked"})
		return r
	}
	add("platform", runtime.GOOS == "linux" && runtime.GOARCH == "amd64", runtime.GOOS+"/"+runtime.GOARCH)
	existing := p.WorkDir
	for {
		_, err := os.Stat(existing)
		if err == nil {
			break
		}
		parent := filepath.Dir(existing)
		if parent == existing {
			break
		}
		existing = parent
	}
	var stat syscall.Statfs_t
	err := syscall.Statfs(existing, &stat)
	add("workspace-space", err == nil && stat.Bavail*uint64(stat.Bsize) >= 1<<30, "at least 1 GiB free on workspace filesystem; no directory created")
	var server struct {
		Version    string
		APIVersion string
		Os         string
		Arch       string
	}
	err = probe(ctx, &server, "version", "--format", "{{json .Server}}")
	add("docker-engine", err == nil && server.Os == "linux" && server.Arch == "amd64", "local Linux/amd64 Docker engine required")
	if err == nil {
		r.Checks[len(r.Checks)-1].Detail = "Docker " + server.Version + "; API " + server.APIVersion
	}
	var compose struct{ Version string }
	err = probe(ctx, &compose, "compose", "version", "--format", "json")
	add("compose-v2", err == nil && strings.HasPrefix(strings.TrimPrefix(compose.Version, "v"), "2."), "Compose v2 required")
	if err == nil {
		r.Checks[len(r.Checks)-1].Detail = compose.Version
	}
	var info struct {
		NCPU          int
		MemTotal      int64
		DockerRootDir string
	}
	err = probe(ctx, &info, "info", "--format", "{{json .}}")
	add("engine-capacity", err == nil && info.NCPU >= 2 && info.MemTotal >= 2<<30, "minimum 2 CPUs / 2 GiB engine RAM for this template")
	diskErr := syscall.Statfs(info.DockerRootDir, &stat)
	add("docker-storage", err == nil && diskErr == nil && stat.Bavail*uint64(stat.Bsize) >= 1<<30, "at least 1 GiB free on local Docker storage filesystem")
	for role, image := range map[string]string{"postgres": p.Images.Postgres, "app": p.Images.App} {
		var entries []struct {
			ID   string `json:"Id"`
			OS   string `json:"Os"`
			Arch string `json:"Architecture"`
		}
		err = probe(ctx, &entries, "image", "inspect", image)
		ok := err == nil && len(entries) == 1 && entries[0].OS == "linux" && entries[0].Arch == "amd64"
		add("image-"+role, ok, "immutable image must already exist locally as linux/amd64; doctor never pulls")
	}
	return r
}
