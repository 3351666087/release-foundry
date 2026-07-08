package gointegration

import (
	"encoding/json"
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
