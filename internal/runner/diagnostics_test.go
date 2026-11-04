package runner

import (
	"strings"
	"testing"
)

func TestDiagnosticsNeverCopiesRawContent(t *testing.T) {
	lines := safeLogLines("SECRET password=abc\nSECRET database system is ready to accept connections\nTraceback (most recent call last): SECRET\n")
	joined := strings.Join(lines, "\n")
	if strings.Contains(joined, "SECRET") || strings.Contains(joined, "abc") || !strings.Contains(joined, "ready to accept") {
		t.Fatal(joined)
	}
}
