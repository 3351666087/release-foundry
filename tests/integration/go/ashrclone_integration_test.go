package gointegration

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	ashrclone "github.com/ashr-labs/ashr/packages/go/ashrclone"
)

func TestGoSDKRuntimeDTOParitySmoke(t *testing.T) {
	service := ashrclone.NewMemoryService()
	input := ashrclone.AgentInputFromParts([]ashrclone.AgentInputPart{
		{Type: ashrclone.ModalityText, Text: "grade this workflow"},
		{Type: ashrclone.ModalityAudio, URL: "https://example.invalid/audio.wav", MIMEType: "audio/wav"},
		{Type: ashrclone.ModalityFile, Path: "fixtures/spec.pdf", MIMEType: "application/pdf"},
		{Type: ashrclone.ModalityImage, Path: "fixtures/image.png", MIMEType: "image/png"},
		{Type: ashrclone.ModalityVideo, URL: "https://example.invalid/video.mp4", MIMEType: "video/mp4"},
	}, ashrclone.JSONMap{"source": "go_integration"})
	boot, err := service.BootstrapProject("Tenant", "Project", ashrclone.Dataset{Name: "Dataset", Cases: []ashrclone.DatasetCase{{CaseID: "case_1", Input: input}}}, "tenant_go", "project_go")
	if err != nil {
		t.Fatal(err)
	}
	run, err := service.SubmitRun("tenant_go", "project_go", boot.Result.Dataset.DatasetID, "agent:go", "run_go", nil, ashrclone.IdempotencyOptions{Key: "idem_go"})
	if err != nil {
		t.Fatal(err)
	}
	if run.Result.Status != "queued" {
		t.Fatalf("status = %q", run.Result.Status)
	}
	payload, err := json.Marshal(boot)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"tenant_id", "project_id", "dataset_id", "schema_version", "audio", "file", "image", "video"} {
		if !strings.Contains(string(payload), want) {
			t.Fatalf("bootstrap payload missing %q: %s", want, payload)
		}
	}
}

func TestGoSDKHostedUploadParityAndMediaSafety(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.EscapedPath() != "/v1/projects/project_go/runs/run_go/upload" {
			t.Fatalf("unexpected request target %s %s", r.Method, r.URL.EscapedPath())
		}
		if r.Header.Get("Idempotency-Key") != "idem_upload" || r.Header.Get("X-Request-ID") != "req_upload" {
			t.Fatalf("missing idempotency/request headers: %#v", r.Header)
		}
		var body ashrclone.JSONMap
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body["tenant_id"] != "tenant_go" || body["upload_id"] != "upload_go" {
			t.Fatalf("unexpected upload body: %#v", body)
		}
		result, ok := body["result"].(map[string]any)
		if !ok || result["artifact_url"] != "https://example.invalid/artifact.json" {
			t.Fatalf("unexpected result envelope: %#v", body["result"])
		}
		_, _ = w.Write([]byte(`{"uploaded":true}`))
	}))
	defer server.Close()

	client := ashrclone.NewClient(ashrclone.WithBaseURL(server.URL))
	response, err := client.UploadRunHTTP(context.Background(), "tenant_go", "project_go", "run_go", ashrclone.JSONMap{"artifact_url": "https://example.invalid/artifact.json"}, ashrclone.UploadRunOptions{UploadID: "upload_go", IdempotencyKey: "idem_upload", RequestID: "req_upload"})
	if err != nil {
		t.Fatal(err)
	}
	if response.Operation != "upload_run" || response.Result["uploaded"] != true {
		t.Fatalf("unexpected hosted response: %#v", response)
	}

	_, err = client.UploadRunHTTP(context.Background(), "tenant_go", "project_go", "run_go", ashrclone.JSONMap{"data_url": "data:image/png;base64,iVBORw0KGgo="}, ashrclone.UploadRunOptions{IdempotencyKey: "idem_upload_2"})
	var mediaErr ashrclone.MediaSafetyError
	if !errors.As(err, &mediaErr) {
		t.Fatalf("expected media safety error, got %T %v", err, err)
	}
}
