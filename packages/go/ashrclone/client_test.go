package ashrclone

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
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

func TestHostedSubmitRunHTTPUsesParityEnvelopeHeadersAndBody(t *testing.T) {
	secret := "sk-" + "test-secret"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("method = %s", r.Method)
		}
		if r.URL.Path != "/v1/projects/project go/sdk-submit" || r.URL.EscapedPath() != "/v1/projects/project%20go/sdk-submit" {
			t.Fatalf("path = %q", r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer "+secret {
			t.Fatalf("Authorization = %q", got)
		}
		if got := r.Header.Get("Idempotency-Key"); got != "idem-submit" {
			t.Fatalf("Idempotency-Key = %q", got)
		}
		var body JSONMap
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		metadata, ok := body["metadata"].(map[string]any)
		if !ok || metadata["client"] != SaaSClientVersion || metadata["purpose"] != "test" {
			t.Fatalf("metadata = %#v", body["metadata"])
		}
		for key, want := range map[string]any{"tenant_id": "tenant_go", "dataset_id": "dataset_go", "agent_ref": "agent:go", "run_id": "run_go", "api_key_id": "key_go", "idempotency_key": "idem-submit", "request_id": "req-go"} {
			if got := body[key]; got != want {
				t.Fatalf("%s = %#v, want %#v in %#v", key, got, want, body)
			}
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"run_id":"run_go","status":"queued"}`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithAPIKey(secret))
	response, err := client.SubmitRunHTTP(context.Background(), "tenant_go", "project go", SubmitRunOptions{DatasetID: "dataset_go", AgentRef: "agent:go", RunID: "run_go", Metadata: JSONMap{"purpose": "test"}, APIKeyID: "key_go", IdempotencyKey: "idem-submit", RequestID: "req-go"})
	if err != nil {
		t.Fatal(err)
	}
	if response.Operation != "sdk_submit" || response.Status != "ok" || response.Result["status"] != "queued" {
		t.Fatalf("unexpected envelope: %#v", response)
	}
}

func TestHostedWorkerJobHTTPUsesControlPlaneRoutesHeadersAndBody(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("method = %s", r.Method)
		}
		if r.URL.EscapedPath() != "/v1/projects/project%20go/worker-jobs/enqueue" {
			t.Fatalf("path = %q", r.URL.EscapedPath())
		}
		if got := r.Header.Get("Idempotency-Key"); got != "idem-worker" {
			t.Fatalf("Idempotency-Key = %q", got)
		}
		if got := r.Header.Get("X-Request-ID"); got != "req-worker" {
			t.Fatalf("X-Request-ID = %q", got)
		}
		var body JSONMap
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		payload, ok := body["payload"].(map[string]any)
		if !ok || payload["action"] != "release_gate" {
			t.Fatalf("payload = %#v", body["payload"])
		}
		for key, want := range map[string]any{"tenant_id": "tenant_go", "job_type": "release_gate", "target_id": "run_go", "job_id": "job_go", "api_key_id": "key_go", "idempotency_key": "idem-worker", "request_id": "req-worker"} {
			if got := body[key]; got != want {
				t.Fatalf("%s = %#v, want %#v in %#v", key, got, want, body)
			}
		}
		if body["priority"] != float64(10) || body["max_attempts"] != float64(4) {
			t.Fatalf("priority/max_attempts = %#v/%#v", body["priority"], body["max_attempts"])
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"job_id":"job_go","status":"queued","payload_sha256":"abc","raw_payload_included":false}`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL))
	response, err := client.EnqueueWorkerJobHTTP(context.Background(), "tenant_go", "project go", JSONMap{"action": "release_gate"}, EnqueueWorkerJobHTTPOptions{JobType: "release_gate", TargetID: "run_go", JobID: "job_go", Priority: 10, MaxAttempts: 4, APIKeyID: "key_go", IdempotencyKey: "idem-worker", RequestID: "req-worker"})
	if err != nil {
		t.Fatal(err)
	}
	if response.Operation != "worker.job.enqueue" || response.Result["status"] != "queued" || response.Result["raw_payload_included"] != false {
		t.Fatalf("unexpected worker envelope: %#v", response)
	}

	_, err = client.EnqueueWorkerJobHTTP(context.Background(), "tenant_go", "project go", JSONMap{"data_url": "data:image/png;base64,iVBORw0KGgo="}, EnqueueWorkerJobHTTPOptions{JobType: "release_gate", IdempotencyKey: "idem-worker-2"})
	var mediaErr MediaSafetyError
	if !errors.As(err, &mediaErr) {
		t.Fatalf("expected media safety error, got %T %v", err, err)
	}
}

func TestClientRetriesRetryableStatusWithIdempotency(t *testing.T) {
	attempts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts++
		if attempts == 1 {
			http.Error(w, `{"message":"temporary"}`, http.StatusServiceUnavailable)
			return
		}
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithRetry(2, time.Millisecond), WithRetrySleeper(func(context.Context, time.Duration) error { return nil }))
	var response JSONMap
	if err := client.Post(context.Background(), "retry", JSONMap{"ok": true}, &response, IdempotencyOptions{Key: "idem-retry"}); err != nil {
		t.Fatal(err)
	}
	if attempts != 2 || response["ok"] != true {
		t.Fatalf("attempts=%d response=%#v", attempts, response)
	}
}

func TestClientRefusesRetryingMutationWithoutIdempotency(t *testing.T) {
	client := NewClient(WithRetry(1, 0))
	var response JSONMap
	err := client.Post(context.Background(), "unsafe", JSONMap{"ok": true}, &response, IdempotencyOptions{})
	var safety RetrySafetyError
	if !errors.As(err, &safety) {
		t.Fatalf("expected RetrySafetyError, got %T %v", err, err)
	}
}

func TestAPIErrorIsTypedRetryableAndRedacted(t *testing.T) {
	secret := "sk-" + "test-secret"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "1")
		w.WriteHeader(http.StatusTooManyRequests)
		_, _ = w.Write([]byte(`{"message":"Bearer ` + secret + `","api_key":"` + secret + `"}`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithRetry(0, 0))
	var response JSONMap
	err := client.Get(context.Background(), "limited", JSONMap{"tenant_id": "tenant"}, &response, IdempotencyOptions{})
	var apiErr APIError
	if !errors.As(err, &apiErr) {
		t.Fatalf("expected APIError, got %T %v", err, err)
	}
	if !apiErr.Retryable() || apiErr.Headers["retry_after"] != "1" {
		t.Fatalf("unexpected retry metadata: %#v", apiErr)
	}
	encoded, marshalErr := json.Marshal(apiErr.Response)
	if marshalErr != nil {
		t.Fatal(marshalErr)
	}
	if strings.Contains(apiErr.Error(), secret) || strings.Contains(string(encoded), secret) {
		t.Fatalf("api error leaked secret: %s %#v", apiErr.Error(), apiErr.Response)
	}
}
