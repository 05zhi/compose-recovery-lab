package doctor

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/05zhi/compose-recovery-lab/internal/planner"
	"os"
	"path/filepath"
	"testing"
)

func TestReadinessNegatives(t *testing.T) {
	for _, scenario := range []string{"ready", "offline", "unavailable", "old-api", "old-compose", "low-memory", "missing-image", "wrong-arch", "workspace-file", "shared-workspace"} {
		t.Run(scenario, func(t *testing.T) {
			root := t.TempDir()
			p := planner.Plan{WorkDir: filepath.Join(root, "new-work")}
			if scenario == "workspace-file" {
				os.WriteFile(p.WorkDir, []byte("no"), 0600)
			}
			if scenario == "shared-workspace" {
				os.Mkdir(p.WorkDir, 0700)
				os.Chmod(p.WorkDir, 0777)
			}
			calls := 0
			query := func(ctx context.Context, out any, args ...string) error {
				calls++
				if scenario == "offline" {
					t.Fatal("offline doctor queried Docker")
				}
				if scenario == "unavailable" {
					return errors.New("DO_NOT_DISCLOSE_THIS")
				}
				var raw string
				switch args[0] {
				case "version":
					api := "1.52"
					if scenario == "old-api" {
						api = "1.43"
					}
					raw = `{"Version":"29.1.3","APIVersion":"` + api + `","Os":"linux","Arch":"amd64"}`
				case "compose":
					version := "2.40.3"
					if scenario == "old-compose" {
						version = "1.29.2"
					}
					raw = `{"Version":"` + version + `"}`
				case "info":
					mem := int64(4 << 30)
					if scenario == "low-memory" {
						mem = 512 << 20
					}
					b, _ := json.Marshal(map[string]any{"NCPU": 2, "MemTotal": mem, "DockerRootDir": root})
					raw = string(b)
				case "image":
					if scenario == "missing-image" {
						return errors.New("missing")
					}
					arch := "amd64"
					if scenario == "wrong-arch" {
						arch = "arm64"
					}
					raw = `[{"Id":"test","Os":"linux","Architecture":"` + arch + `"}]`
				default:
					t.Fatal("non-read-only Docker operation", args)
				}
				return json.Unmarshal([]byte(raw), out)
			}
			result := checkPlan(context.Background(), p, scenario == "offline", query)
			if result.Ready != (scenario == "ready") {
				t.Fatal(scenario, result)
			}
			if scenario == "offline" && (calls != 0 || result.Status != "offline_valid") {
				t.Fatal(result)
			}
			if scenario != "workspace-file" && scenario != "shared-workspace" {
				if _, err := os.Stat(p.WorkDir); !os.IsNotExist(err) {
					t.Fatal("doctor created workspace")
				}
			}
		})
	}
}
