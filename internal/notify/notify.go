// Package notify delivers only redacted terminal failure summaries.
package notify

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"time"
)

type Event struct {
	Version      int    `json:"version"`
	AttemptID    string `json:"attempt_id"`
	Verification string `json:"verification_result"`
	Cleanup      string `json:"cleanup_result"`
}

func Failure(report []byte) (Event, bool, error) {
	var r struct {
		AttemptID    string `json:"attempt_id"`
		RunID        string `json:"run_id"`
		Phase        string `json:"phase"`
		Verification string `json:"verification_result"`
		Cleanup      string `json:"cleanup_result"`
	}
	if err := json.Unmarshal(report, &r); err != nil {
		return Event{}, false, errors.New("invalid report")
	}
	if r.Phase != "finished" {
		return Event{}, false, errors.New("attempt is not terminal")
	}
	if r.AttemptID == "" {
		r.AttemptID = r.RunID
	}
	return Event{1, r.AttemptID, r.Verification, r.Cleanup}, r.Verification != "passed" || r.Cleanup != "complete", nil
}
func Send(ctx context.Context, endpoint string, event Event) error {
	u, e := url.Parse(endpoint)
	if e != nil || u.User != nil || u.Fragment != "" || u.Host == "" || (u.Scheme != "https" && !(u.Scheme == "http" && (u.Hostname() == "127.0.0.1" || u.Hostname() == "localhost" || u.Hostname() == "::1"))) {
		return errors.New("webhook requires HTTPS or loopback HTTP")
	}
	body, _ := json.Marshal(event)
	req, e := http.NewRequestWithContext(ctx, "POST", endpoint, bytes.NewReader(body))
	if e != nil {
		return errors.New("invalid webhook")
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Idempotency-Key", event.AttemptID)
	client := &http.Client{Timeout: 10 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	response, e := client.Do(req)
	if e != nil {
		return errors.New("webhook delivery failed; endpoint omitted")
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return errors.New("webhook rejected delivery")
	}
	return nil
}
