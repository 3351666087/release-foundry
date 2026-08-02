package releasefoundry

import "time"

const (
	localAPIKeySecretPrefix    = "local-test-secret-"
	ScopeRunSubmit             = "run:submit"
	ScopeRunUpload             = "run:upload"
	ScopeTraceIngest           = "trace:ingest"
	ScopeRunLifecycleRead      = "run:lifecycle:read"
	ScopeUsageRead             = "usage:read"
	ScopeBillingWrite          = "billing:write"
	ScopeBillingRead           = "billing:read"
	ScopeBillingWebhookIngest  = "billing:webhook"
	ScopeAuditRead             = "audit:read"
	ScopeEvidenceRead          = "evidence:read"
	ScopeWorkerJobEnqueue      = "worker_job:enqueue"
	ScopeWorkerJobLease        = "worker_job:lease"
	ScopeWorkerJobComplete     = "worker_job:complete"
	ScopeWorkerJobFail         = "worker_job:fail"
	ScopeWorkerJobList         = "worker_job:list"
	ScopeArtifactManifestRead  = "artifact_manifest:read"
	ScopeArtifactManifestWrite = "artifact_manifest:write"
	ScopeAPIKeyWrite           = "api_key:write"
	ScopeAPIKeyRead            = "api_key:read"
	ScopeAPIKeyPreflight       = "api_key:preflight"
)

type APIKeyHandle struct {
	TenantID  string   `json:"tenant_id"`
	ProjectID string   `json:"project_id,omitempty"`
	KeyID     string   `json:"key_id"`
	Scopes    []string `json:"scopes,omitempty"`
}

type AuthzError struct {
	Code    string
	Message string
}

func (err AuthzError) Error() string {
	if err.Message != "" {
		return err.Message
	}
	if err.Code != "" {
		return err.Code
	}
	return "authorization failed"
}

type APIKeyRecord struct {
	SchemaVersion string     `json:"schema_version"`
	TenantID      string     `json:"tenant_id"`
	ProjectID     string     `json:"project_id"`
	KeyID         string     `json:"key_id"`
	Name          string     `json:"name"`
	SecretPrefix  string     `json:"secret_prefix"`
	SecretSHA256  string     `json:"secret_sha256,omitempty"`
	Scopes        []string   `json:"scopes"`
	Revoked       bool       `json:"revoked"`
	CreatedAt     time.Time  `json:"created_at"`
	LastUsedAt    *time.Time `json:"last_used_at,omitempty"`
}

type APIKeyCreateResult struct {
	SchemaVersion          string       `json:"schema_version"`
	APIKey                 APIKeyRecord `json:"api_key"`
	OneTimeSecret          string       `json:"one_time_secret,omitempty"`
	OneTimeSecretDisplayed bool         `json:"one_time_secret_displayed"`
}

type APIKeyListResult struct {
	SchemaVersion string         `json:"schema_version"`
	TenantID      string         `json:"tenant_id"`
	ProjectID     string         `json:"project_id"`
	APIKeys       []APIKeyRecord `json:"api_keys"`
	Count         int            `json:"count"`
}

type APIKeyVerifyResult struct {
	SchemaVersion      string       `json:"schema_version"`
	TenantID           string       `json:"tenant_id"`
	ProjectID          string       `json:"project_id"`
	KeyID              string       `json:"key_id"`
	Authenticated      bool         `json:"authenticated"`
	Scope              string       `json:"scope,omitempty"`
	SecretValuePresent bool         `json:"secret_value_present"`
	APIKey             APIKeyRecord `json:"api_key,omitempty"`
}

type APIKeyRateLimit struct {
	SchemaVersion string    `json:"schema_version"`
	TenantID      string    `json:"tenant_id"`
	ProjectID     string    `json:"project_id"`
	KeyID         string    `json:"key_id"`
	Operation     string    `json:"operation"`
	Limit         int       `json:"limit"`
	Used          int       `json:"used"`
	Remaining     int       `json:"remaining"`
	UpdatedAt     time.Time `json:"updated_at"`
}

type APIKeyRateLimitSnapshot struct {
	SchemaVersion string            `json:"schema_version"`
	TenantID      string            `json:"tenant_id"`
	ProjectID     string            `json:"project_id"`
	KeyID         string            `json:"key_id,omitempty"`
	RateLimits    []APIKeyRateLimit `json:"rate_limits"`
	Count         int               `json:"count"`
}

type PreflightOptions struct {
	TenantID  string `json:"tenant_id"`
	ProjectID string `json:"project_id"`
	KeyID     string `json:"key_id,omitempty"`
	Scope     string `json:"scope,omitempty"`
	Operation string `json:"operation,omitempty"`
	Units     int    `json:"units,omitempty"`
}

type AuthPreflight struct {
	SchemaVersion string           `json:"schema_version"`
	TenantID      string           `json:"tenant_id"`
	ProjectID     string           `json:"project_id"`
	KeyID         string           `json:"key_id,omitempty"`
	Scope         string           `json:"scope,omitempty"`
	Scopes        []string         `json:"scopes,omitempty"`
	Operation     string           `json:"operation,omitempty"`
	Allowed       bool             `json:"allowed"`
	Quota         *APIKeyRateLimit `json:"quota,omitempty"`
	CheckedAt     time.Time        `json:"checked_at"`
}

type AuthPrincipal struct {
	TenantID  string       `json:"tenant_id"`
	ProjectID string       `json:"project_id,omitempty"`
	APIKey    APIKeyHandle `json:"api_key_handle"`
	Scopes    []string     `json:"scopes,omitempty"`
}

func (principal AuthPrincipal) APIKeyID() string {
	return principal.APIKey.KeyID
}
