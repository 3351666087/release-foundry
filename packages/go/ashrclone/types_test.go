package ashrclone

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestAgentInputKeepsModalitiesEqualAndDerivesText(t *testing.T) {
	input := AgentInputFromParts([]AgentInputPart{
		{Type: ModalityText, Text: "Describe this file."},
		{Type: ModalityAudio, URL: "https://example.invalid/audio.wav", MIMEType: "audio/wav"},
		{Type: ModalityFile, Path: "fixtures/spec.pdf", Name: "spec.pdf", MIMEType: "application/pdf"},
		{Type: ModalityImage, Path: "fixtures/image.png", MIMEType: "image/png"},
		{Type: ModalityVideo, URL: "https://example.invalid/video.mp4", MIMEType: "video/mp4"},
	}, JSONMap{"case": "multi_modal"})
	if err := input.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
	payload, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}
	text := string(payload)
	for _, want := range []string{`"schema_version":"ashr.clone.agent_input.v1"`, `"type":"text"`, `"type":"audio"`, `"type":"file"`, `"type":"image"`, `"type":"video"`} {
		if !strings.Contains(text, want) {
			t.Fatalf("payload missing %s: %s", want, text)
		}
	}
	if !strings.Contains(text, `"text":"Describe this file."`) {
		t.Fatalf("payload did not derive top-level text: %s", text)
	}
}

func TestRedactSensitiveRemovesEnvKeyValues(t *testing.T) {
	secret := "sk" + "-live-do-not-print"
	redacted := RedactSensitive(JSONMap{"api_key": secret, "nested": JSONMap{"Authorization": "Bearer " + secret}})
	payload, err := json.Marshal(redacted)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(payload), secret) || strings.Contains(string(payload), "Bearer ") {
		t.Fatalf("redacted payload leaked secret material: %s", payload)
	}
	if strings.Count(string(payload), Redacted) != 2 {
		t.Fatalf("expected redaction markers, got %s", payload)
	}
}
