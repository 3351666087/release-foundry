package ashrclone

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
)

type CreateAPIKeyOptions struct {
	Name         string   `json:"name"`
	Scopes       []string `json:"scopes"`
	KeyID        string   `json:"key_id,omitempty"`
	AuthKeyID    string   `json:"auth_key_id,omitempty"`
	RevealSecret bool     `json:"reveal_secret,omitempty"`
	APIKey       string   `json:"-"`
}

type ListAPIKeysOptions struct {
	AuthKeyID string `json:"auth_key_id,omitempty"`
}

type VerifyAPIKeySecretOptions struct {
	KeyID  string `json:"-"`
	Secret string `json:"secret"`
	Scope  string `json:"scope,omitempty"`
}

type ConfigureAPIKeyRateLimitOptions struct {
	KeyID     string `json:"-"`
	Operation string `json:"operation"`
	Limit     int    `json:"limit"`
	Period    string `json:"period,omitempty"`
	AuthKeyID string `json:"auth_key_id,omitempty"`
}

type APIKeyRateLimitSnapshotOptions struct {
	KeyID string `json:"key_id,omitempty"`
}

type SubmitRunOptions struct {
	DatasetID      string  `json:"dataset_id"`
	AgentRef       string  `json:"agent_ref"`
	RunID          string  `json:"run_id,omitempty"`
	Metadata       JSONMap `json:"metadata,omitempty"`
	APIKeyID       string  `json:"api_key_id,omitempty"`
	APIKey         string  `json:"-"`
	IdempotencyKey string  `json:"idempotency_key,omitempty"`
	RequestID      string  `json:"request_id,omitempty"`
}

type UploadRunOptions struct {
	UploadID       string `json:"upload_id,omitempty"`
	APIKeyID       string `json:"api_key_id,omitempty"`
	APIKey         string `json:"-"`
	IdempotencyKey string `json:"idempotency_key,omitempty"`
	RequestID      string `json:"request_id,omitempty"`
}

type IngestTraceOptions struct {
	BatchID        string `json:"batch_id,omitempty"`
	APIKeyID       string `json:"api_key_id,omitempty"`
	APIKey         string `json:"-"`
	IdempotencyKey string `json:"idempotency_key,omitempty"`
	RequestID      string `json:"request_id,omitempty"`
}

type AuthKeyOptions struct {
	AuthKeyID string `json:"auth_key_id,omitempty"`
}

type AuditLogOptions struct {
	RunID        string `json:"run_id,omitempty"`
	ActionPrefix string `json:"action_prefix,omitempty"`
	AuthKeyID    string `json:"auth_key_id,omitempty"`
	Limit        int    `json:"limit,omitempty"`
}

type VerifyAuditChainOptions struct {
	AuthKeyID string `json:"auth_key_id,omitempty"`
	RequestID string `json:"request_id,omitempty"`
}

type ReleaseGateOptions struct {
	Evaluator                 string  `json:"evaluator,omitempty"`
	MinScore                  float64 `json:"min_score,omitempty"`
	RequiredTraceCompleteness float64 `json:"required_trace_completeness,omitempty"`
	AuthKeyID                 string  `json:"auth_key_id,omitempty"`
	RequestID                 string  `json:"request_id,omitempty"`
}

type VerifyReleaseEvidencePacketOptions struct {
	AuthKeyID string  `json:"auth_key_id,omitempty"`
	Packet    JSONMap `json:"packet,omitempty"`
	RequestID string  `json:"request_id,omitempty"`
}

type ArtifactManifestOptions struct {
	ArtifactID     string `json:"artifact_id,omitempty"`
	APIKeyID       string `json:"api_key_id,omitempty"`
	IdempotencyKey string `json:"idempotency_key,omitempty"`
	RequestID      string `json:"request_id,omitempty"`
}

func (client *Client) CreateAPIKey(ctx context.Context, tenantID, projectID string, options CreateAPIKeyOptions) (Envelope[JSONMap], error) {
	if err := rejectRawAPIKey(options.APIKey); err != nil {
		return Envelope[JSONMap]{}, err
	}
	body := JSONMap{"tenant_id": tenantID, "name": options.Name, "scopes": options.Scopes, "key_id": options.KeyID, "auth_key_id": options.AuthKeyID, "reveal_secret": options.RevealSecret}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "api-keys"), "create_api_key", body, IdempotencyOptions{})
}

func (client *Client) ListAPIKeys(ctx context.Context, tenantID, projectID string, options ListAPIKeysOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "auth_key_id": options.AuthKeyID}
	return client.hosted(ctx, http.MethodGet, projectPath(projectID, "api-keys"), "list_api_keys", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true})
}

func (client *Client) VerifyAPIKeySecret(ctx context.Context, tenantID, projectID string, options VerifyAPIKeySecretOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "secret": options.Secret, "scope": options.Scope}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "api-keys", options.KeyID, "verify"), "verify_api_key_secret", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true})
}

func (client *Client) ConfigureAPIKeyRateLimit(ctx context.Context, tenantID, projectID string, options ConfigureAPIKeyRateLimitOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "operation": options.Operation, "limit": options.Limit, "period": options.Period, "auth_key_id": options.AuthKeyID}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "api-keys", options.KeyID, "rate-limit"), "configure_api_key_rate_limit", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true})
}

func (client *Client) APIKeyRateLimitSnapshot(ctx context.Context, tenantID, projectID string, options APIKeyRateLimitSnapshotOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "key_id": options.KeyID}
	return client.hosted(ctx, http.MethodGet, projectPath(projectID, "api-keys", "rate-limits"), "api_key_rate_limit_snapshot", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true})
}

func (client *Client) SubmitRunHTTP(ctx context.Context, tenantID, projectID string, options SubmitRunOptions) (Envelope[JSONMap], error) {
	if err := rejectRawAPIKey(options.APIKey); err != nil {
		return Envelope[JSONMap]{}, err
	}
	metadata := JSONMap{"client": SaaSClientVersion}
	for key, value := range options.Metadata {
		metadata[key] = value
	}
	body := JSONMap{"tenant_id": tenantID, "dataset_id": options.DatasetID, "agent_ref": options.AgentRef, "run_id": options.RunID, "metadata": metadata, "api_key_id": options.APIKeyID, "idempotency_key": options.IdempotencyKey, "request_id": options.RequestID}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "sdk-submit"), "sdk_submit", body, idemFromHosted(options.IdempotencyKey, options.RequestID, options.APIKeyID))
}

func (client *Client) UploadRunHTTP(ctx context.Context, tenantID, projectID, runID string, result JSONMap, options UploadRunOptions) (Envelope[JSONMap], error) {
	if err := rejectRawAPIKey(options.APIKey); err != nil {
		return Envelope[JSONMap]{}, err
	}
	if err := ValidateMediaSafeEnvelope(result); err != nil {
		return Envelope[JSONMap]{}, err
	}
	body := JSONMap{"tenant_id": tenantID, "result": result, "upload_id": options.UploadID, "api_key_id": options.APIKeyID, "idempotency_key": options.IdempotencyKey, "request_id": options.RequestID}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "runs", runID, "upload"), "upload_run", body, idemFromHosted(options.IdempotencyKey, options.RequestID, options.APIKeyID))
}

func (client *Client) IngestTraceHTTP(ctx context.Context, tenantID, projectID, runID string, observations []JSONMap, options IngestTraceOptions) (Envelope[JSONMap], error) {
	if err := rejectRawAPIKey(options.APIKey); err != nil {
		return Envelope[JSONMap]{}, err
	}
	body := JSONMap{"tenant_id": tenantID, "observations": observations, "batch_id": options.BatchID, "api_key_id": options.APIKeyID, "idempotency_key": options.IdempotencyKey, "request_id": options.RequestID}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "runs", runID, "trace-events"), "ingest_trace", body, idemFromHosted(options.IdempotencyKey, options.RequestID, options.APIKeyID))
}

func (client *Client) LifecycleHTTP(ctx context.Context, tenantID, projectID, runID string) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID}
	return client.hosted(ctx, http.MethodGet, projectPath(projectID, "runs", runID, "lifecycle"), "lifecycle", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true})
}

func (client *Client) UsageHTTP(ctx context.Context, tenantID, projectID string, options AuthKeyOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "auth_key_id": options.AuthKeyID}
	return client.hosted(ctx, http.MethodGet, projectPath(projectID, "usage"), "usage", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true})
}

func (client *Client) AuditLogHTTP(ctx context.Context, tenantID, projectID string, options AuditLogOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "run_id": options.RunID, "action_prefix": options.ActionPrefix, "auth_key_id": options.AuthKeyID, "limit": options.Limit}
	return client.hosted(ctx, http.MethodGet, projectPath(projectID, "audit-log"), "audit_log", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true})
}

func (client *Client) VerifyAuditChainHTTP(ctx context.Context, tenantID, projectID string, options VerifyAuditChainOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "auth_key_id": options.AuthKeyID, "request_id": options.RequestID}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "audit-chain", "verify"), "audit_chain_verify", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true, RequestID: options.RequestID})
}

func (client *Client) EvaluateReleaseGateHTTP(ctx context.Context, tenantID, projectID, runID string, options ReleaseGateOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "evaluator": options.Evaluator, "min_score": options.MinScore, "required_trace_completeness": options.RequiredTraceCompleteness, "auth_key_id": options.AuthKeyID, "request_id": options.RequestID}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "runs", runID, "release-gate"), "release_gate", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true, RequestID: options.RequestID})
}

func (client *Client) BuildReleaseEvidencePacketHTTP(ctx context.Context, tenantID, projectID, runID string, options AuthKeyOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "auth_key_id": options.AuthKeyID}
	return client.hosted(ctx, http.MethodGet, projectPath(projectID, "runs", runID, "release-evidence"), "release_evidence", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true})
}

func (client *Client) VerifyReleaseEvidencePacketHTTP(ctx context.Context, tenantID, projectID, runID string, options VerifyReleaseEvidencePacketOptions) (Envelope[JSONMap], error) {
	if err := ValidateMediaSafeEnvelope(options.Packet); err != nil {
		return Envelope[JSONMap]{}, err
	}
	body := JSONMap{"tenant_id": tenantID, "auth_key_id": options.AuthKeyID, "packet": options.Packet, "request_id": options.RequestID}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "runs", runID, "release-evidence", "verify"), "release_evidence_verify", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true, RequestID: options.RequestID})
}

func (client *Client) CreateArtifactManifestHTTP(ctx context.Context, tenantID, projectID, runID string, manifest JSONMap, options ArtifactManifestOptions) (Envelope[JSONMap], error) {
	if err := ValidateMediaSafeEnvelope(manifest); err != nil {
		return Envelope[JSONMap]{}, err
	}
	body := JSONMap{"tenant_id": tenantID, "manifest": manifest, "artifact_id": options.ArtifactID, "api_key_id": options.APIKeyID, "idempotency_key": options.IdempotencyKey, "request_id": options.RequestID}
	return client.hosted(ctx, http.MethodPost, projectPath(projectID, "runs", runID, "artifact-manifests"), "artifact_manifest", body, idemFromHosted(options.IdempotencyKey, options.RequestID, options.APIKeyID))
}

func (client *Client) ListArtifactManifestsHTTP(ctx context.Context, tenantID, projectID, runID string, options AuthKeyOptions) (Envelope[JSONMap], error) {
	body := JSONMap{"tenant_id": tenantID, "auth_key_id": options.AuthKeyID}
	return client.hosted(ctx, http.MethodGet, projectPath(projectID, "runs", runID, "artifact-manifests"), "artifact_manifests", body, IdempotencyOptions{AllowRetryWithoutIdempotency: true})
}

func (client *Client) hosted(ctx context.Context, method, path, operation string, request JSONMap, options IdempotencyOptions) (Envelope[JSONMap], error) {
	var result JSONMap
	if err := client.DoJSON(ctx, method, path, omitEmptyJSONMap(request), &result, options); err != nil {
		return Envelope[JSONMap]{}, err
	}
	return Envelope[JSONMap]{Operation: operation, Status: "ok", Result: result}, nil
}

func idemFromHosted(key, requestID, apiKeyID string) IdempotencyOptions {
	return IdempotencyOptions{Key: key, RequestID: requestID, APIKeyID: apiKeyID}
}

func projectPath(projectID string, parts ...string) string {
	segments := []string{"v1", "projects", projectID}
	segments = append(segments, parts...)
	path := ""
	for _, segment := range segments {
		path += "/" + url.PathEscape(segment)
	}
	return path
}

func rejectRawAPIKey(apiKey string) error {
	if apiKey != "" {
		return fmt.Errorf("raw api keys are not accepted in request options; configure Client.APIKey or ASHR_API_KEY instead")
	}
	return nil
}

func omitEmptyJSONMap(input JSONMap) JSONMap {
	output := JSONMap{}
	for key, value := range input {
		if isEmptyJSONValue(value) {
			continue
		}
		output[key] = value
	}
	return output
}

func isEmptyJSONValue(value any) bool {
	switch typed := value.(type) {
	case nil:
		return true
	case string:
		return typed == ""
	case int:
		return typed == 0
	case float64:
		return typed == 0
	case []string:
		return typed == nil
	case JSONMap:
		return typed == nil
	default:
		return false
	}
}
