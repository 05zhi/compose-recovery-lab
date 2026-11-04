package planner

import (
	"archive/tar"
	"encoding/json"
	"github.com/05zhi/compose-recovery-lab/internal/config"
	"github.com/05zhi/compose-recovery-lab/internal/source"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func setup(t *testing.T) config.Config {
	t.Helper()
	root := t.TempDir()
	bundle := filepath.Join(root, "bundle")
	os.Mkdir(bundle, 0700)
	os.WriteFile(filepath.Join(bundle, "database.dump"), []byte("PGDMPunit-test"), 0600)
	os.WriteFile(filepath.Join(bundle, "app-config.sanitized.json"), []byte("{}"), 0600)
	f, _ := os.Create(filepath.Join(bundle, "uploads.tar"))
	tw := tar.NewWriter(f)
	tw.WriteHeader(&tar.Header{Name: "document.txt", Mode: 0644, Size: 2})
	tw.Write([]byte("ok"))
	tw.Close()
	f.Close()
	now := time.Now().UTC()
	m := source.Manifest{SchemaVersion: 1, BackupID: "unit", AppVersion: "document-app-v1", PostgresMajor: 17, PostgresImage: "postgres@sha256:" + strings.Repeat("a", 64), AppImage: "sha256:" + strings.Repeat("b", 64), Extensions: []string{"plpgsql"}, StartedAt: now, FinishedAt: now, AttachmentCount: 1, Consistency: "synthetic"}
	if err := source.WriteManifest(bundle, m); err != nil {
		t.Fatal(err)
	}
	lock := filepath.Join(root, "images.json")
	os.WriteFile(lock, []byte(`{"postgres":"`+m.PostgresImage+`","app":"`+m.AppImage+`"}`), 0600)
	c := config.Config{Name: "test", Template: "document-app-v1", Hash: strings.Repeat("c", 64)}
	c.Backup.Path = bundle
	c.Backup.Mapping = map[string]string{"database": "database.dump", "uploads": "uploads.tar", "app_config": "app-config.sanitized.json"}
	c.Runtime.ImagesFile = lock
	c.Runtime.WorkDir = filepath.Join(root, "not-created")
	c.Runtime.Timeout = "10m"
	return c
}
func TestReadOnlyPlan(t *testing.T) {
	c := setup(t)
	p, err := Build(c)
	if err != nil {
		t.Fatal(err)
	}
	if len(p.Mapping) != 3 || p.EnvironmentChecked || p.ManifestHash == "" {
		t.Fatal(p)
	}
	if _, err = os.Stat(c.Runtime.WorkDir); !os.IsNotExist(err) {
		t.Fatal("plan created workspace")
	}
	b, _ := json.Marshal(p)
	if strings.Contains(string(b), "DATABASE_URL") {
		t.Fatal("secret-bearing runtime spec in plan")
	}
}
func TestMappingAndPathFailures(t *testing.T) {
	for _, name := range []string{"missing-role", "wrong-source", "traversal", "overlap", "symlink-overlap", "bad-image", "duplicate-lock", "changed-image"} {
		t.Run(name, func(t *testing.T) {
			c := setup(t)
			switch name {
			case "missing-role":
				delete(c.Backup.Mapping, "uploads")
			case "wrong-source":
				c.Backup.Mapping["uploads"] = "database.dump"
			case "traversal":
				c.Backup.Mapping["database"] = "../database.dump"
			case "overlap":
				c.Runtime.WorkDir = c.Backup.Path
			case "symlink-overlap":
				link := filepath.Join(filepath.Dir(c.Backup.Path), "alias")
				os.Symlink(c.Backup.Path, link)
				c.Runtime.WorkDir = filepath.Join(link, "runs")
			case "bad-image":
				os.WriteFile(c.Runtime.ImagesFile, []byte(`{"postgres":"postgres:17","app":"latest"}`), 0600)
			case "duplicate-lock":
				os.WriteFile(c.Runtime.ImagesFile, []byte(`{"app":"one","app":"two","postgres":"three"}`), 0600)
			case "changed-image":
				b, _ := os.ReadFile(c.Runtime.ImagesFile)
				os.WriteFile(c.Runtime.ImagesFile, []byte(strings.Replace(string(b), strings.Repeat("b", 64), strings.Repeat("d", 64), 1)), 0600)
			}
			if _, err := Build(c); err == nil {
				t.Fatal("invalid mapping accepted")
			}
		})
	}
}
