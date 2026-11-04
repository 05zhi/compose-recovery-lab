package source

import (
	"archive/tar"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func fixture(t *testing.T) string {
	t.Helper()
	d := t.TempDir()
	os.WriteFile(filepath.Join(d, "database.dump"), []byte("PGDMPsynthetic-unit-fixture"), 0600)
	os.WriteFile(filepath.Join(d, "app-config.sanitized.json"), []byte("{}"), 0600)
	tarfile(t, d, "file.txt", tar.TypeReg)
	now := time.Now().UTC()
	m := Manifest{SchemaVersion: 1, BackupID: "test", AppVersion: "document-app-v1", PostgresMajor: 17, AppImage: "sha256:" + strings.Repeat("a", 64), PostgresImage: "postgres@sha256:" + strings.Repeat("b", 64), Extensions: []string{"plpgsql"}, StartedAt: now, FinishedAt: now, Consistency: "test", AttachmentCount: 1}
	if err := WriteManifest(d, m); err != nil {
		t.Fatal(err)
	}
	return d
}
func tarfile(t *testing.T, d, name string, kind byte) {
	t.Helper()
	f, err := os.Create(filepath.Join(d, "uploads.tar"))
	if err != nil {
		t.Fatal(err)
	}
	tw := tar.NewWriter(f)
	h := &tar.Header{Name: name, Mode: 0644, Typeflag: kind}
	if kind == tar.TypeReg {
		h.Size = 2
	}
	if kind == tar.TypeSymlink {
		h.Linkname = "/etc/passwd"
	}
	if err = tw.WriteHeader(h); err != nil {
		t.Fatal(err)
	}
	if kind == tar.TypeReg {
		tw.Write([]byte("ok"))
	}
	tw.Close()
	f.Close()
}
func TestStageAndCorruption(t *testing.T) {
	src := fixture(t)
	dst := filepath.Join(t.TempDir(), "staged")
	if _, err := Stage(src, dst); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(src, "database.dump"), []byte("PGDMPbad"), 0600)
	if _, err := Stage(src, filepath.Join(t.TempDir(), "bad")); err == nil {
		t.Fatal("accepted corrupt dump")
	}
	if _, err := Load(dst); err != nil {
		t.Fatal("source mutation affected private copy", err)
	}
}
func TestUnsafeTar(t *testing.T) {
	for _, name := range []string{"../escape", "/absolute", "a/../../escape", "C:/file", "a\\file"} {
		t.Run(name, func(t *testing.T) {
			d := t.TempDir()
			tarfile(t, d, name, tar.TypeReg)
			if _, err := ValidateTar(filepath.Join(d, "uploads.tar")); err == nil {
				t.Fatal("accepted traversal")
			}
		})
	}
	d := t.TempDir()
	tarfile(t, d, "link", tar.TypeSymlink)
	if _, err := ValidateTar(filepath.Join(d, "uploads.tar")); err == nil {
		t.Fatal("accepted link")
	}
}
func TestPartialAndSymlink(t *testing.T) {
	src := fixture(t)
	if _, err := Stage(src+".partial", filepath.Join(t.TempDir(), "stage")); err == nil {
		t.Fatal("accepted partial")
	}
	name := filepath.Join(src, "database.dump")
	os.Remove(name)
	if err := os.Symlink("uploads.tar", name); err != nil {
		t.Skip(err)
	}
	if _, err := Stage(src, filepath.Join(t.TempDir(), "stage")); err == nil {
		t.Fatal("accepted symlink")
	}
}
