package ashrclone

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"
)

const (
	AgentInputSchemaVersion   = "ashr.clone.agent_input.v1"
	SaaSClientVersion         = "ashr.clone.saas_ingestion_client.v1"
	ControlPlaneSchemaVersion = "ashr.clone.saas_control_plane.v1"
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

type RunUpload struct {
	SchemaVersion      string    `json:"schema_version"`
	TenantID           string    `json:"tenant_id"`
	ProjectID          string    `json:"project_id"`
	RunID              string    `json:"run_id"`
	UploadID           string    `json:"upload_id"`
	ResultSHA256       string    `json:"result_sha256"`
	RawPayloadIncluded bool      `json:"raw_payload_included"`
	APIKeyID           string    `json:"api_key_id,omitempty"`
	RequestID          string    `json:"request_id,omitempty"`
	CreatedAt          time.Time `json:"created_at"`
}

type TraceBatch struct {
	SchemaVersion      string    `json:"schema_version"`
	TenantID           string    `json:"tenant_id"`
	ProjectID          string    `json:"project_id"`
	RunID              string    `json:"run_id"`
	BatchID            string    `json:"batch_id"`
	ObservationCount   int       `json:"observation_count"`
	ObservationsSHA256 string    `json:"observations_sha256"`
	RawPayloadIncluded bool      `json:"raw_payload_included"`
	APIKeyID           string    `json:"api_key_id,omitempty"`
	RequestID          string    `json:"request_id,omitempty"`
	CreatedAt          time.Time `json:"created_at"`
}

type ArtifactManifest struct {
	SchemaVersion      string    `json:"schema_version"`
	TenantID           string    `json:"tenant_id"`
	ProjectID          string    `json:"project_id"`
	RunID              string    `json:"run_id"`
	ArtifactID         string    `json:"artifact_id"`
	ManifestSHA256     string    `json:"manifest_sha256"`
	RawPayloadIncluded bool      `json:"raw_payload_included"`
	APIKeyID           string    `json:"api_key_id,omitempty"`
	RequestID          string    `json:"request_id,omitempty"`
	CreatedAt          time.Time `json:"created_at"`
}

type ArtifactManifestList struct {
	SchemaVersion string             `json:"schema_version"`
	TenantID      string             `json:"tenant_id"`
	ProjectID     string             `json:"project_id"`
	RunID         string             `json:"run_id"`
	Manifests     []ArtifactManifest `json:"manifests"`
	Count         int                `json:"count"`
}

const (
	WorkerJobStatusQueued       = "queued"
	WorkerJobStatusLeased       = "leased"
	WorkerJobStatusRetrying     = "retrying"
	WorkerJobStatusCompleted    = "completed"
	WorkerJobStatusDeadLettered = "dead_lettered"
	WorkerJobStatusCancelled    = "cancelled"
)

type WorkerJob struct {
	SchemaVersion      string          `json:"schema_version"`
	JobID              string          `json:"job_id"`
	TenantID           string          `json:"tenant_id"`
	ProjectID          string          `json:"project_id"`
	JobType            string          `json:"job_type"`
	TargetID           string          `json:"target_id,omitempty"`
	PayloadSHA256      string          `json:"payload_sha256"`
	RawPayloadIncluded bool            `json:"raw_payload_included"`
	Status             string          `json:"status"`
	Priority           int             `json:"priority"`
	Attempts           int             `json:"attempts"`
	MaxAttempts        int             `json:"max_attempts"`
	LeaseOwnerID       string          `json:"lease_owner_id,omitempty"`
	LeaseExpiresAt     *time.Time      `json:"lease_expires_at,omitempty"`
	AvailableAt        *time.Time      `json:"available_at,omitempty"`
	LastError          *WorkerJobError `json:"last_error,omitempty"`
	ResultSHA256       string          `json:"result_sha256,omitempty"`
	IdempotencyKey     string          `json:"idempotency_key,omitempty"`
	RequestID          string          `json:"request_id,omitempty"`
	CreatedAt          time.Time       `json:"created_at"`
	UpdatedAt          time.Time       `json:"updated_at"`
	CompletedAt        *time.Time      `json:"completed_at,omitempty"`
	DeadLetteredAt     *time.Time      `json:"dead_lettered_at,omitempty"`
}

type WorkerJobError struct {
	SHA256             string    `json:"sha256"`
	Type               string    `json:"type"`
	Message            string    `json:"message"`
	RawPayloadIncluded bool      `json:"raw_payload_included"`
	FailedAt           time.Time `json:"failed_at"`
}

type WorkerLeaseResult struct {
	SchemaVersion string     `json:"schema_version"`
	Status        string     `json:"status"`
	TenantID      string     `json:"tenant_id"`
	ProjectID     string     `json:"project_id"`
	Leased        bool       `json:"leased"`
	Job           *WorkerJob `json:"job"`
	CreatedAt     time.Time  `json:"created_at,omitempty"`
}

type WorkerJobList struct {
	SchemaVersion string      `json:"schema_version"`
	TenantID      string      `json:"tenant_id"`
	ProjectID     string      `json:"project_id"`
	Filters       JSONMap     `json:"filters"`
	Jobs          []WorkerJob `json:"jobs"`
	Count         int         `json:"count"`
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
