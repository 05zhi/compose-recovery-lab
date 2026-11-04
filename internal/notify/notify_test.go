package notify

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestFailureDelivery(t *testing.T) {
	e, send, err := Failure([]byte(`{"attempt_id":"test","phase":"finished","verification_result":"failed","cleanup_result":"complete","error":"SECRET"}`))
	if err != nil || !send {
		t.Fatal(err)
	}
	received := false
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		if strings.Contains(string(b), "SECRET") || r.Header.Get("Idempotency-Key") != "test" {
			t.Error("invalid payload")
		}
		received = true
		w.WriteHeader(204)
	}))
	defer s.Close()
	if err = Send(context.Background(), s.URL, e); err != nil || !received {
		t.Fatal(err)
	}
	if Send(context.Background(), "http://example.com/hook", e) == nil {
		t.Fatal("accepted cleartext remote endpoint")
	}
}
func TestNoSuccessOrPendingNotification(t *testing.T) {
	_, send, e := Failure([]byte(`{"phase":"finished","verification_result":"passed","cleanup_result":"complete"}`))
	if e != nil || send {
		t.Fatal("success notification")
	}
	_, _, e = Failure([]byte(`{"phase":"restoring"}`))
	if e == nil {
		t.Fatal("pending notification")
	}
}
func TestNoRedirect(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { http.Redirect(w, r, "http://127.0.0.1:1/", 302) }))
	defer s.Close()
	if Send(context.Background(), s.URL, Event{}) == nil {
		t.Fatal("redirect accepted")
	}
}
