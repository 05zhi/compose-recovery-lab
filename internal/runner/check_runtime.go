package runner

import (
	"context"
	"errors"
	"github.com/05zhi/compose-recovery-lab/internal/checks"
	"io"
	"strings"
)

type checkKey struct{}

func CheckContext(ctx context.Context, specs []checks.Spec) context.Context {
	return context.WithValue(ctx, checkKey{}, specs)
}
func (s *Session) checkRole(ctx context.Context, db string) error {
	sql := "CREATE ROLE crl_check LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD '" + s.password + "'; REVOKE TEMPORARY ON DATABASE documents FROM PUBLIC; REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT CONNECT ON DATABASE documents TO crl_check; GRANT USAGE ON SCHEMA public TO crl_check; GRANT SELECT ON ALL TABLES IN SCHEMA public TO crl_check; ALTER ROLE crl_check SET default_transaction_read_only = on; ALTER ROLE crl_check SET statement_timeout = '5s';"
	return docker(ctx, strings.NewReader(sql), io.Discard, "exec", "-i", db, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "bootstrap", "-d", "documents")
}

// Known assertion failure wins over incomplete evidence. Required skipped/errors never pass.
func Aggregate(specs []checks.Spec, rows []Check) (string, error) {
	expected := map[string]checks.Spec{}
	for _, s := range specs {
		expected[s.ID] = s
	}
	seen := map[string]bool{}
	failed, incomplete := false, false
	for _, r := range rows {
		s, ok := expected[r.ID]
		if !ok || seen[r.ID] || r.Required != s.Required {
			incomplete = true
		}
		seen[r.ID] = true
		switch r.Status {
		case "failed":
			failed = true
		case "passed":
		case "skipped":
			if s.Required {
				incomplete = true
			}
		default:
			incomplete = true
		}
	}
	for id, s := range expected {
		if s.Required && !seen[id] {
			incomplete = true
		}
	}
	if failed {
		return "failed", errors.New("check assertion failed")
	}
	if incomplete {
		return "inconclusive", errors.New("check evidence incomplete")
	}
	return "passed", nil
}

type templateKey struct{}

func TemplateContext(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, templateKey{}, id)
}
func templateFrom(ctx context.Context) string {
	if id, ok := ctx.Value(templateKey{}).(string); ok {
		return id
	}
	return "document-app-v1"
}
