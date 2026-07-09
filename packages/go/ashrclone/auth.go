package ashrclone

const (
	ScopeRunSubmit             = "run:submit"
	ScopeRunUpload             = "run:upload"
	ScopeTraceIngest           = "trace:ingest"
	ScopeUsageRead             = "usage:read"
	ScopeAuditRead             = "audit:read"
	ScopeWorkerJobEnqueue      = "worker_job:enqueue"
	ScopeWorkerJobLease        = "worker_job:lease"
	ScopeWorkerJobComplete     = "worker_job:complete"
	ScopeWorkerJobFail         = "worker_job:fail"
	ScopeWorkerJobList         = "worker_job:list"
	ScopeArtifactManifestRead  = "artifact_manifest:read"
	ScopeArtifactManifestWrite = "artifact_manifest:write"
)

type APIKeyHandle struct {
	TenantID  string   `json:"tenant_id"`
	ProjectID string   `json:"project_id,omitempty"`
	KeyID     string   `json:"key_id"`
	Scopes    []string `json:"scopes,omitempty"`
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
