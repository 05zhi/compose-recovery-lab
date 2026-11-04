// Package planner performs read-only bundle and mapping validation. No Docker calls.
package planner

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"github.com/05zhi/compose-recovery-lab/internal/config"
	"github.com/05zhi/compose-recovery-lab/internal/runner"
	"github.com/05zhi/compose-recovery-lab/internal/safeio"
	"github.com/05zhi/compose-recovery-lab/internal/source"
	"github.com/05zhi/compose-recovery-lab/internal/strictjson"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

type Mapping struct {
	Role   string `json:"role"`
	Source string `json:"source"`
	Target string `json:"target"`
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256"`
}
type Plan struct {
	Version            int            `json:"plan_version"`
	Name               string         `json:"name"`
	Template           string         `json:"template"`
	ConfigHash         string         `json:"config_hash"`
	ManifestHash       string         `json:"manifest_sha256"`
	BackupID           string         `json:"backup_id"`
	Images             runner.Images  `json:"images"`
	Mapping            []Mapping      `json:"source_mapping"`
	Resources          []string       `json:"new_resources"`
	Steps              []string       `json:"steps"`
	Checks             []string       `json:"required_checks"`
	Limits             map[string]any `json:"limits"`
	WorkDir            string         `json:"work_dir"`
	Consistency        string         `json:"consistency"`
	Limitations        []string       `json:"limitations"`
	EnvironmentChecked bool           `json:"environment_checked"`
}

func RealPath(p string) (string, error) {
	p, err := filepath.Abs(p)
	if err != nil {
		return "", err
	}
	tail := []string{}
	for {
		_, err = os.Lstat(p)
		if err == nil {
			real, e := filepath.EvalSymlinks(p)
			if e != nil {
				return "", errors.New("cannot resolve path")
			}
			for i := len(tail) - 1; i >= 0; i-- {
				real = filepath.Join(real, tail[i])
			}
			return real, nil
		}
		if !os.IsNotExist(err) {
			return "", errors.New("path inaccessible")
		}
		parent := filepath.Dir(p)
		if parent == p {
			return "", errors.New("no existing path ancestor")
		}
		tail = append(tail, filepath.Base(p))
		p = parent
	}
}
func within(a, b string) bool {
	relative, err := filepath.Rel(a, b)
	return err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator))
}
func Build(c config.Config) (Plan, error) {
	var p Plan
	backup, err := RealPath(c.Backup.Path)
	if err != nil {
		return p, err
	}
	work, err := RealPath(c.Runtime.WorkDir)
	if err != nil {
		return p, err
	}
	if within(backup, work) || within(work, backup) {
		return p, errors.New("backup and workspace must be disjoint, including symlink aliases")
	}
	if strings.HasSuffix(filepath.Clean(c.Backup.Path), ".partial") || strings.HasSuffix(backup, ".partial") {
		return p, errors.New("partial backup is not published")
	}
	expected := map[string]string{"database": "database.dump", "uploads": "uploads.tar", "app_config": "app-config.sanitized.json"}
	if len(c.Backup.Mapping) != len(expected) {
		return p, errors.New("source mapping must cover exactly database, uploads and app_config")
	}
	for role, file := range expected {
		if c.Backup.Mapping[role] != file {
			return p, errors.New("source mapping does not match document-app-v1 contract")
		}
	}
	lock, err := safeio.Read(c.Runtime.ImagesFile, 4096)
	if err != nil {
		return p, errors.New("image lock must be a bounded regular file")
	}
	var images runner.Images
	if err = strictjson.Decode(lock, &images); err != nil {
		return p, errors.New("image lock must contain exactly postgres and app")
	}
	if !regexp.MustCompile(`^postgres@sha256:[0-9a-f]{64}$`).MatchString(images.Postgres) || !regexp.MustCompile(`^sha256:[0-9a-f]{64}$`).MatchString(images.App) {
		return p, errors.New("image lock must use immutable Linux image references")
	}
	manifestPath := filepath.Join(c.Backup.Path, "manifest.json")
	before, err := safeio.Read(manifestPath, 65536)
	if err != nil {
		return p, err
	}
	manifest, err := source.Load(c.Backup.Path)
	if err != nil {
		return p, err
	}
	after, err := safeio.Read(manifestPath, 65536)
	if err != nil || string(before) != string(after) {
		return p, errors.New("manifest changed during planning")
	}
	if images.Postgres != manifest.PostgresImage || images.App != manifest.AppImage {
		return p, errors.New("manifest images differ from trusted image lock")
	}
	sum := sha256.Sum256(before)
	p = Plan{Version: 1, Name: c.Name, Template: c.Template, ConfigHash: c.Hash, ManifestHash: hex.EncodeToString(sum[:]), BackupID: manifest.BackupID, Images: images, WorkDir: work, Consistency: manifest.Consistency,
		Resources:   []string{"2 containers: db, app (random run ID)", "1 internal network; no published host ports", "2 new volumes: database, uploads; no host bind mounts", "1 private attempt directory; generated credentials never included in plan"},
		Steps:       []string{"verify local images and free space", "copy and revalidate bundle; enforce planned manifest hash", "create fresh PostgreSQL 17 and non-superuser demo role", "restore custom dump without source owner/ACL", "restore validated attachments to uploads volume", "start application and replace synthetic login password", "run all required template checks", "cross-check ownership and remove created resources; write JSON/HTML reports"},
		Limits:      map[string]any{"timeout": c.Runtime.Timeout, "container_memory_bytes": 512 << 20, "container_cpus": 1, "container_pids": 128, "minimum_free_workspace_bytes": 1 << 30, "maximum_bundle_file_bytes": source.MaxFileSize, "maximum_expanded_upload_bytes": source.MaxUploadsSize, "maximum_tar_entries": source.MaxFiles},
		Limitations: []string{"Offline plan only; environment availability checked by doctor, not plan", "Only document-app-v1 and fixed role mappings supported; arbitrary Compose rejected; bounded declarative checks supported", "Hash integrity is not source authenticity or proof of complete application data", "Original owner/ACL and login password are not preserved; no third-party workflow coverage", "Actual resources use a new run ID; cleanup may require manual retry after uncatchable termination"}}
	for _, role := range []string{"database", "uploads", "app_config"} {
		file := expected[role]
		meta := manifest.Files[file]
		target := map[string]string{"database": "postgres:documents (new database volume)", "uploads": "volume:uploads:/uploads (new volume)", "app_config": "informational metadata only; never executed"}[role]
		p.Mapping = append(p.Mapping, Mapping{role, filepath.Join(backup, file), target, meta.Size, meta.SHA256})
	}
	for _, check := range c.Checks {
		p.Checks = append(p.Checks, check.ID)
	}
	return p, nil
}
