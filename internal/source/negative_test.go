package source

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
)

func TestManifestNegatives(t *testing.T) {
	mutations := map[string]func(map[string]any){
		"version":       func(m map[string]any) { m["schema_version"] = 2 },
		"major":         func(m map[string]any) { m["postgres_major"] = 16 },
		"extension":     func(m map[string]any) { m["extensions"] = []string{"postgis"} },
		"missing-count": func(m map[string]any) { delete(m, "attachment_count") },
		"null-count":    func(m map[string]any) { m["attachment_count"] = nil },
		"unknown":       func(m map[string]any) { m["command"] = "SHOULD_NOT_LEAK" },
		"image-tag":     func(m map[string]any) { m["app_image"] = "app:latest" },
		"time":          func(m map[string]any) { m["finished_at"] = "2000-01-01T00:00:00Z" },
		"inventory":     func(m map[string]any) { m["attachment_count"] = 2 },
		"negative-size": func(m map[string]any) { m["files"].(map[string]any)["database.dump"].(map[string]any)["size"] = -1 },
		"filename": func(m map[string]any) {
			files := m["files"].(map[string]any)
			files["../database.dump"] = files["database.dump"]
			delete(files, "database.dump")
		},
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			dir := fixture(t)
			p := filepath.Join(dir, "manifest.json")
			b, _ := os.ReadFile(p)
			var m map[string]any
			json.Unmarshal(b, &m)
			mutate(m)
			b, _ = json.Marshal(m)
			os.WriteFile(p, b, 0600)
			if _, err := Load(dir); err == nil {
				t.Fatal("invalid manifest accepted")
			} else if strings.Contains(err.Error(), "SHOULD_NOT_LEAK") {
				t.Fatal("value leaked")
			}
		})
	}
}
func TestDuplicateAndSpecialFiles(t *testing.T) {
	t.Run("duplicate", func(t *testing.T) {
		d := fixture(t)
		p := filepath.Join(d, "manifest.json")
		b, _ := os.ReadFile(p)
		b = []byte(strings.Replace(string(b), `"schema_version": 1`, `"schema_version": 2, "schema_version": 1`, 1))
		os.WriteFile(p, b, 0600)
		if _, err := Load(d); err == nil {
			t.Fatal("duplicate accepted")
		}
	})
	for _, kind := range []string{"symlink", "fifo", "extra", "large-manifest"} {
		t.Run(kind, func(t *testing.T) {
			d := fixture(t)
			p := filepath.Join(d, "database.dump")
			switch kind {
			case "symlink":
				os.Remove(p)
				os.Symlink("uploads.tar", p)
			case "fifo":
				os.Remove(p)
				if err := syscall.Mkfifo(p, 0600); err != nil {
					t.Fatal(err)
				}
			case "extra":
				os.WriteFile(filepath.Join(d, "extra"), nil, 0600)
			case "large-manifest":
				os.WriteFile(filepath.Join(d, "manifest.json"), make([]byte, 65537), 0600)
			}
			if _, err := Load(d); err == nil {
				t.Fatal("unsafe bundle accepted")
			}
		})
	}
}
