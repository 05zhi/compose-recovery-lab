// Package source implements the bounded, local M1 backup contract.
package source

import (
	"archive/tar"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"

	"github.com/05zhi/compose-recovery-lab/internal/safeio"
	"github.com/05zhi/compose-recovery-lab/internal/strictjson"
)

const MaxFileSize int64 = 256 << 20
const MaxUploadsSize int64 = 64 << 20
const MaxFiles = 10000

var Names = []string{"database.dump", "uploads.tar", "app-config.sanitized.json"}

type File struct {
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256"`
}

type Manifest struct {
	SchemaVersion   int             `json:"schema_version"`
	BackupID        string          `json:"backup_id"`
	AppVersion      string          `json:"app_version"`
	PostgresMajor   int             `json:"postgres_major"`
	PostgresImage   string          `json:"postgres_image"`
	AppImage        string          `json:"app_image"`
	Extensions      []string        `json:"extensions"`
	StartedAt       time.Time       `json:"started_at"`
	FinishedAt      time.Time       `json:"finished_at"`
	AttachmentCount int             `json:"attachment_count"`
	Consistency     string          `json:"consistency"`
	Limitations     []string        `json:"limitations"`
	Files           map[string]File `json:"files"`
}

func Digest(name string) (File, error) {
	f, before, err := safeio.Open(name, MaxFileSize)
	if err != nil {
		return File{}, err
	}
	defer f.Close()
	h := sha256.New()
	n, err := io.Copy(h, io.LimitReader(f, MaxFileSize+1))
	if err != nil {
		return File{}, err
	}
	if n > MaxFileSize {
		return File{}, errors.New("bundle file too large")
	}
	if err = safeio.Verify(name, before); err != nil {
		return File{}, err
	}
	return File{n, hex.EncodeToString(h.Sum(nil))}, nil
}

func WriteManifest(dir string, m Manifest) error {
	if m.Limitations == nil {
		m.Limitations = []string{}
	}
	m.Files = map[string]File{}
	for _, name := range Names {
		f, err := Digest(filepath.Join(dir, name))
		if err != nil {
			return err
		}
		m.Files[name] = f
	}
	data, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(dir, "manifest.json"), append(data, '\n'), 0600)
}

func Load(dir string) (Manifest, error) {
	var m Manifest
	if strings.HasSuffix(filepath.Clean(dir), ".partial") {
		return m, errors.New("unpublished partial bundle")
	}
	info, err := os.Lstat(dir)
	if err != nil || !info.IsDir() {
		return m, errors.New("bundle root must be a directory, not a link")
	}
	entries, err := os.ReadDir(dir)
	if err != nil || len(entries) != 4 {
		return m, errors.New("bundle must contain exactly the four contract files")
	}
	snapshots := map[string]os.FileInfo{}
	for _, name := range append([]string{"manifest.json"}, Names...) {
		limit := MaxFileSize
		if name == "manifest.json" {
			limit = 65536
		}
		f, before, err := safeio.Open(filepath.Join(dir, name), limit)
		if err != nil {
			return m, err
		}
		f.Close()
		snapshots[name] = before
	}
	data, err := safeio.Read(filepath.Join(dir, "manifest.json"), 65536)
	if err != nil {
		return m, err
	}
	if err = strictjson.Decode(data, &m); err != nil {
		return m, err
	}
	if m.SchemaVersion != 1 || m.PostgresMajor != 17 || m.AppVersion != "document-app-v1" || m.BackupID == "" {
		return m, errors.New("unsupported backup contract")
	}
	if len(m.Extensions) != 1 || m.Extensions[0] != "plpgsql" {
		return m, errors.New("unsupported extensions")
	}
	if m.StartedAt.IsZero() || m.FinishedAt.IsZero() || m.FinishedAt.Before(m.StartedAt) || strings.TrimSpace(m.Consistency) == "" {
		return m, errors.New("invalid consistency metadata")
	}
	if m.AttachmentCount < 0 || m.AttachmentCount > MaxFiles || len(m.Files) != len(Names) {
		return m, errors.New("invalid bundle inventory")
	}
	if !validImage(m.AppImage, false) || !validImage(m.PostgresImage, true) {
		return m, errors.New("images must use immutable IDs/digests")
	}
	for _, name := range Names {
		want, ok := m.Files[name]
		if !ok || want.Size < 0 || want.Size > MaxFileSize || len(want.SHA256) != 64 {
			return m, errors.New("missing or invalid file metadata")
		}
		got, err := Digest(filepath.Join(dir, name))
		if err != nil {
			return m, err
		}
		if got != want {
			return m, fmt.Errorf("integrity mismatch: %s", name)
		}
	}
	dump, _, err := safeio.Open(filepath.Join(dir, "database.dump"), MaxFileSize)
	if err != nil {
		return m, err
	}
	magic := make([]byte, 5)
	_, err = io.ReadFull(dump, magic)
	dump.Close()
	if err != nil || string(magic) != "PGDMP" {
		return m, errors.New("expected PostgreSQL custom-format dump")
	}
	count, err := ValidateTar(filepath.Join(dir, "uploads.tar"))
	if err != nil {
		return m, err
	}
	if count != m.AttachmentCount {
		return m, errors.New("attachment inventory mismatch")
	}
	for name, before := range snapshots {
		if err = safeio.Verify(filepath.Join(dir, name), before); err != nil {
			return m, err
		}
	}
	return m, nil
}

func validImage(s string, repository bool) bool {
	prefix := "sha256:"
	if repository {
		prefix = "postgres@sha256:"
	}
	if !strings.HasPrefix(s, prefix) || len(s) != len(prefix)+64 {
		return false
	}
	_, err := hex.DecodeString(strings.TrimPrefix(s, prefix))
	return err == nil
}

// Stage copies fixed regular files to a private fresh directory before validation.
// Stat checks detect ordinary source replacement; hashes bind the staged bytes.
func Stage(src, dst string) (Manifest, error) {
	var zero Manifest
	if strings.HasSuffix(filepath.Clean(src), ".partial") {
		return zero, errors.New("unpublished partial bundle")
	}
	if err := os.Mkdir(dst, 0700); err != nil {
		return zero, err
	}
	for _, name := range append([]string{"manifest.json"}, Names...) {
		from := filepath.Join(src, name)
		before, err := os.Lstat(from)
		if err != nil {
			return zero, err
		}
		if !before.Mode().IsRegular() || before.Size() > MaxFileSize {
			return zero, errors.New("source must be bounded regular files")
		}
		if name == "manifest.json" && before.Size() > 65536 {
			return zero, errors.New("manifest too large")
		}
		in, _, err := safeio.Open(from, MaxFileSize)
		if err != nil {
			return zero, err
		}
		opened, err := in.Stat()
		if err != nil || !os.SameFile(before, opened) {
			in.Close()
			return zero, errors.New("source changed before copy")
		}
		out, err := os.OpenFile(filepath.Join(dst, name), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if err != nil {
			in.Close()
			return zero, err
		}
		n, copyErr := io.Copy(out, io.LimitReader(in, MaxFileSize+1))
		closeErr := out.Close()
		in.Close()
		if copyErr != nil {
			return zero, copyErr
		}
		if closeErr != nil {
			return zero, closeErr
		}
		after, err := os.Lstat(from)
		if err != nil || !os.SameFile(before, after) || n != before.Size() || !before.ModTime().Equal(after.ModTime()) || after.Size() != before.Size() {
			return zero, errors.New("source changed during copy")
		}
	}
	return Load(dst)
}

func SafeName(name string) bool {
	return name != "" && name != "." && !strings.ContainsAny(name, "\\:") && !path.IsAbs(name) && path.Clean(name) == name && name != ".." && !strings.HasPrefix(name, "../")
}

// ValidateTar rejects all links, special files, duplicates, traversal and expansion bombs.
func ValidateTar(filename string) (count int, err error) {
	f, before, err := safeio.Open(filename, MaxFileSize)
	if err != nil {
		return 0, err
	}
	defer f.Close()
	defer func() {
		if err == nil {
			err = safeio.Verify(filename, before)
		}
	}()
	tr := tar.NewReader(f)
	seen := map[string]bool{}
	var total int64
	count = 0
	for {
		h, err := tr.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			return 0, err
		}
		name := strings.TrimSuffix(h.Name, "/")
		if !SafeName(name) || seen[name] {
			return 0, errors.New("unsafe or duplicate tar path")
		}
		seen[name] = true
		if len(seen) > MaxFiles {
			return 0, errors.New("tar entry limit exceeded")
		}
		if h.Typeflag != tar.TypeReg && h.Typeflag != tar.TypeDir {
			return 0, errors.New("tar links and special entries are unsupported")
		}
		if h.Mode&07000 != 0 || h.Size < 0 {
			return 0, errors.New("unsafe tar metadata")
		}
		if h.Size > MaxUploadsSize-total {
			return 0, errors.New("tar expansion limit exceeded")
		}
		total += h.Size
		if h.Typeflag == tar.TypeReg {
			count++
		}
		if _, err = io.Copy(io.Discard, tr); err != nil {
			return 0, err
		}
	}
	return count, nil
}
