package config

import (
	"path/filepath"
	"strings"
	"testing"
)

const example = `schema_version: 1
name: documents
template: document-app-v1
backup:
  type: local_bundle
  path: ./backup
  mapping:
    database: database.dump
    uploads: uploads.tar
    app_config: app-config.sanitized.json
runtime:
  images_file: ./images.lock.json
  work_dir: ./work
  timeout: 10m
checks:
  - {id: sql-documents, required: true}
  - {id: database-files, required: true}
  - {id: login-search-download, required: true}
  - {id: external-connectivity, required: true}
report:
  formats: [json, html]
`

func TestValidAndRelativePaths(t *testing.T) {
	base := t.TempDir()
	c, err := Parse([]byte(example), base)
	if err != nil {
		t.Fatal(err)
	}
	if c.Backup.Path != filepath.Join(base, "backup") || len(c.Hash) != 64 {
		t.Fatal(c)
	}
	other, err := Parse([]byte("# comment\n"+example), base)
	if err != nil || other.Hash != c.Hash {
		t.Fatal("comments changed semantic hash")
	}
}
func TestRejectInvalid(t *testing.T) {
	cases := map[string]string{
		"version":         strings.Replace(example, "schema_version: 1", "schema_version: 2", 1),
		"type":            strings.Replace(example, "schema_version: 1", "schema_version: '1'", 1),
		"unknown":         "privileged: true\n" + example,
		"duplicate":       example + "name: other\n",
		"multidoc":        example + "---\nname: other\n",
		"anchor":          strings.Replace(example, "name: documents", "name: &name documents", 1),
		"merge":           "<<: {privileged: true}\n" + example,
		"null":            strings.Replace(example, "timeout: 10m", "timeout: null", 1),
		"duration":        strings.Replace(example, "timeout: 10m", "timeout: 2h", 1),
		"env":             strings.Replace(example, "./backup", "${SECRET}", 1),
		"mapping":         strings.Replace(example, "database: database.dump", "database: /etc/passwd", 1),
		"optional":        strings.Replace(example, "required: true", "required: false", 1),
		"duplicate-check": strings.Replace(example, "database-files", "sql-documents", 1),
		"query":           example + "query: SELECT secret\n",
		"missing":         strings.Replace(example, "  formats: [json, html]", "  formats: [json]", 1),
		"secret":          example + "password: SHOULD_NEVER_APPEAR\n",
		"oversize":        strings.Repeat(" ", 65537),
	}
	for name, input := range cases {
		t.Run(name, func(t *testing.T) {
			_, err := Parse([]byte(input), t.TempDir())
			if err == nil {
				t.Fatal("accepted invalid configuration")
			}
			if strings.Contains(err.Error(), "SHOULD_NEVER_APPEAR") {
				t.Fatal("secret leaked")
			}
		})
	}
}
func TestPublishedExample(t *testing.T) {
	if _, err := Load("../../examples/document-app/drill.yaml"); err != nil {
		t.Fatal(err)
	}
}
