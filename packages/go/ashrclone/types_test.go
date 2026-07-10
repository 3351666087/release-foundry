package ashrclone

import (
	"encoding/json"
	"errors"
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
	redacted := RedactSensitive(JSONMap{"api_key": secret, "nested": JSONMap{"Authorization": "Bearer " + secret}, "message": "provider failed with password=" + secret})
	payload, err := json.Marshal(redacted)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(payload), secret) || strings.Contains(string(payload), "Bearer ") || strings.Contains(string(payload), "password=") {
		t.Fatalf("redacted payload leaked secret material: %s", payload)
	}
	if strings.Count(string(payload), Redacted) != 3 {
		t.Fatalf("expected redaction markers, got %s", payload)
	}
}

func TestRedactSensitiveRemovesAssignmentsInFreeText(t *testing.T) {
	redacted := RedactSensitive("provider failed password=super-secret secret:top token=abc bearer credential")
	text := strings.ToLower(redacted.(string))
	for _, forbidden := range []string{"super-secret", "secret:top", "token=abc", "bearer credential", "password="} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("free-text redaction leaked %q in %q", forbidden, text)
		}
	}
}
func TestMediaSafeEnvelopeRejectsInlineBytesAndAllowsReferences(t *testing.T) {
	if err := ValidateMediaSafeEnvelope(JSONMap{"artifact": JSONMap{"url": "https://example.invalid/image.png", "mime_type": "image/png"}}); err != nil {
		t.Fatalf("reference envelope rejected: %v", err)
	}
	unsafe := JSONMap{"artifact": JSONMap{"data_url": "data:image/png;base64,iVBORw0KGgo="}}
	err := ValidateMediaSafeEnvelope(unsafe)
	var mediaErr MediaSafetyError
	if !errors.As(err, &mediaErr) {
		t.Fatalf("expected MediaSafetyError, got %T %v", err, err)
	}
}

func TestAgentInputRequiresMediaReferences(t *testing.T) {
	input := AgentInputFromParts([]AgentInputPart{{Type: ModalityImage, MIMEType: "image/png"}}, nil)
	if err := input.Validate(); err == nil || !strings.Contains(err.Error(), "url or path") {
		t.Fatalf("expected media reference validation error, got %v", err)
	}
}
