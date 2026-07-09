package ashrclone

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

const (
	AgentInputSchemaVersion = "ashr.clone.agent_input.v1"
	SaaSClientVersion       = "ashr.clone.saas_ingestion_client.v1"
)

type JSONMap map[string]any

type Modality string

const (
	ModalityText  Modality = "text"
	ModalityAudio Modality = "audio"
	ModalityFile  Modality = "file"
	ModalityImage Modality = "image"
	ModalityVideo Modality = "video"
)

var supportedModalities = map[Modality]struct{}{
	ModalityText:  {},
	ModalityAudio: {},
	ModalityFile:  {},
	ModalityImage: {},
	ModalityVideo: {},
}

type Tenant struct {
	TenantID string  `json:"tenant_id"`
	Name     string  `json:"name"`
	Metadata JSONMap `json:"metadata,omitempty"`
}

type Project struct {
	TenantID  string  `json:"tenant_id"`
	ProjectID string  `json:"project_id"`
	Name      string  `json:"name"`
	Metadata  JSONMap `json:"metadata,omitempty"`
}

type Dataset struct {
	TenantID  string        `json:"tenant_id"`
	ProjectID string        `json:"project_id"`
	DatasetID string        `json:"dataset_id"`
	Name      string        `json:"name"`
	Cases     []DatasetCase `json:"cases,omitempty"`
	Metadata  JSONMap       `json:"metadata,omitempty"`
}

type DatasetCase struct {
	CaseID   string     `json:"case_id"`
	Input    AgentInput `json:"input"`
	Expected JSONMap    `json:"expected,omitempty"`
	Metadata JSONMap    `json:"metadata,omitempty"`
}

type Run struct {
	TenantID  string  `json:"tenant_id"`
	ProjectID string  `json:"project_id"`
	DatasetID string  `json:"dataset_id"`
	RunID     string  `json:"run_id"`
	AgentRef  string  `json:"agent_ref"`
	Status    string  `json:"status"`
	Metadata  JSONMap `json:"metadata,omitempty"`
}

type BootstrapResult struct {
	Tenant  Tenant  `json:"tenant"`
	Project Project `json:"project"`
	Dataset Dataset `json:"dataset"`
}

type AgentInput struct {
	SchemaVersion string           `json:"schema_version"`
	Text          string           `json:"text"`
	Parts         []AgentInputPart `json:"parts"`
	Metadata      JSONMap          `json:"metadata,omitempty"`
}

type AgentInputPart struct {
	Type     Modality `json:"type"`
	Text     string   `json:"text,omitempty"`
	URL      string   `json:"url,omitempty"`
	Path     string   `json:"path,omitempty"`
	Name     string   `json:"name,omitempty"`
	MIMEType string   `json:"mime_type,omitempty"`
	Metadata JSONMap  `json:"metadata,omitempty"`
}

func TextInput(text string, metadata JSONMap) AgentInput {
	return AgentInputFromParts([]AgentInputPart{{Type: ModalityText, Text: text}}, metadata)
}

func AgentInputFromParts(parts []AgentInputPart, metadata JSONMap) AgentInput {
	input := AgentInput{SchemaVersion: AgentInputSchemaVersion, Parts: append([]AgentInputPart(nil), parts...), Metadata: cloneMap(metadata)}
	input.Text = textFromParts(input.Parts)
	return input
}

func (input AgentInput) Validate() error {
	for index, part := range input.Parts {
		if _, ok := supportedModalities[part.Type]; !ok {
			return fmt.Errorf("agent input part %d has unsupported modality %q", index, part.Type)
		}
		if part.Type != ModalityText && part.URL == "" && part.Path == "" {
			return fmt.Errorf("agent input part %d with modality %q must use url or path media reference", index, part.Type)
		}
		if err := ValidateMediaSafeEnvelope(part.Metadata); err != nil {
			return fmt.Errorf("agent input part %d metadata: %w", index, err)
		}
	}
	if err := ValidateMediaSafeEnvelope(input.Metadata); err != nil {
		return fmt.Errorf("agent input metadata: %w", err)
	}
	return nil
}

func (input AgentInput) MarshalJSON() ([]byte, error) {
	type alias AgentInput
	copy := alias(input)
	if copy.SchemaVersion == "" {
		copy.SchemaVersion = AgentInputSchemaVersion
	}
	if copy.Parts == nil {
		copy.Parts = []AgentInputPart{}
	}
	if copy.Text == "" {
		copy.Text = textFromParts(copy.Parts)
	}
	return json.Marshal(copy)
}

func textFromParts(parts []AgentInputPart) string {
	texts := make([]string, 0, len(parts))
	for _, part := range parts {
		if part.Type == ModalityText && strings.TrimSpace(part.Text) != "" {
			texts = append(texts, part.Text)
		}
	}
	return strings.Join(texts, "\n")
}

func stableJSON(value any) ([]byte, error) {
	normalized := normalizeJSON(value)
	return json.Marshal(normalized)
}

func normalizeJSON(value any) any {
	switch typed := value.(type) {
	case JSONMap:
		return normalizeMap(map[string]any(typed))
	case map[string]any:
		return normalizeMap(typed)
	case []any:
		items := make([]any, 0, len(typed))
		for _, item := range typed {
			items = append(items, normalizeJSON(item))
		}
		return items
	default:
		return typed
	}
}

func normalizeMap(input map[string]any) map[string]any {
	keys := make([]string, 0, len(input))
	for key := range input {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	output := make(map[string]any, len(input))
	for _, key := range keys {
		output[key] = normalizeJSON(input[key])
	}
	return output
}

func cloneMap(input JSONMap) JSONMap {
	if input == nil {
		return nil
	}
	output := make(JSONMap, len(input))
	for key, value := range input {
		output[key] = value
	}
	return output
}
