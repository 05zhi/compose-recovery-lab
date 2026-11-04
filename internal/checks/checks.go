// Package checks defines bounded declarative checks executed inside the isolated app.
package checks

import (
	_ "embed"
	"errors"
	"regexp"
	"strings"
)

type Expect struct {
	Operator string `json:"operator"`
	Value    any    `json:"value"`
}
type Scope struct {
	Mode string `json:"mode"`
	Size int    `json:"size,omitempty"`
	Seed int64  `json:"seed,omitempty"`
}
type Spec struct {
	ID       string  `json:"id"`
	Required bool    `json:"required"`
	Type     string  `json:"type,omitempty"`
	Query    string  `json:"query,omitempty"`
	Expect   *Expect `json:"expect,omitempty"`
	Path     string  `json:"path,omitempty"`
	SHA256   string  `json:"sha256,omitempty"`
	Root     string  `json:"root,omitempty"`
	Scope    *Scope  `json:"scope,omitempty"`
	Status   int     `json:"status,omitempty"`
	Contains string  `json:"contains,omitempty"`
}

//go:embed probe.py
var Program string

func Validate(specs []Spec) error {
	ids := map[string]bool{}
	for _, s := range specs {
		if ids[s.ID] {
			return errors.New("check IDs must be unique")
		}
		ids[s.ID] = true
		if s.Type == "" {
			continue
		}
		if s.Type == "sql" || s.Type == "database_files" {
			if len(s.Query) > 4096 || !regexp.MustCompile(`(?is)^\s*select\s`).MatchString(s.Query) {
				return errors.New("queries must be bounded SELECT expressions")
			}
		}
		if s.Type == "file" && (!safePath(s.Path) || s.Root != "uploads") {
			return errors.New("file path must remain below uploads")
		}
		if s.Type == "http" && (!strings.HasPrefix(s.Path, "/") || strings.HasPrefix(s.Path, "//") || strings.ContainsAny(s.Path, "\r\n\\") || strings.Contains(s.Path, "://")) {
			return errors.New("HTTP checks accept only local application paths")
		}
	}
	return nil
}
func safePath(s string) bool {
	if s == "" || strings.HasPrefix(s, "/") || strings.ContainsAny(s, "\\:") {
		return false
	}
	for _, p := range strings.Split(s, "/") {
		if p == ".." || p == "." || p == "" {
			return false
		}
	}
	return true
}
