package ashrclone

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestClientPostSendsAuthAndIdempotencyButRedactedConfigDoesNotLeak(t *testing.T) {
	secret := "sk" + "-test-secret"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer "+secret {
			t.Fatalf("Authorization header = %q", got)
		}
		if got := r.Header.Get("Idempotency-Key"); got != "idem-http" {
			t.Fatalf("Idempotency-Key = %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithAPIKey(secret))
	var response map[string]bool
	if err := client.Post(context.Background(), "sdk_submit", JSONMap{"hello": "world"}, &response, IdempotencyOptions{Key: "idem-http"}); err != nil {
		t.Fatal(err)
	}
	config, err := json.Marshal(client.RedactedConfig())
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(config), secret) || !strings.Contains(string(config), Redacted) {
		t.Fatalf("redacted config leaked or missed marker: %s", config)
	}
}
