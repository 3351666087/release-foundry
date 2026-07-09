package gointegration

import (
	"context"
	"os"
	"testing"

	ashrclone "github.com/ashr-labs/ashr/packages/go/ashrclone"
)

func TestPostgresAPIKeyLifecycleLiveOptIn(t *testing.T) {
	dsn := os.Getenv("A1_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("set A1_POSTGRES_TEST_DSN to run live Postgres API key lifecycle proof")
	}
	repository, err := ashrclone.OpenPostgresRepository(dsn)
	if err != nil {
		t.Fatalf("open postgres repository: %v", err)
	}
	defer repository.Close()
	if err := repository.Migrate(context.Background()); err != nil {
		t.Fatalf("migrate postgres repository: %v", err)
	}

	boot, err := repository.BootstrapProject("Tenant", "Keys", ashrclone.Dataset{Name: "Dataset", Cases: []ashrclone.DatasetCase{{CaseID: "case_live_key", Input: ashrclone.AgentInputFromParts([]ashrclone.AgentInputPart{{Type: ashrclone.ModalityText, Text: "live key proof"}}, nil)}}}, "tenant_live_keys", "project_live_keys")
	if err != nil {
		t.Fatalf("bootstrap: %v", err)
	}
	key, err := repository.CreateAPIKey(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, ashrclone.CreateAPIKeyOptions{KeyID: "key_live_submit", Name: "Live submitter", Scopes: []string{ashrclone.ScopeRunSubmit}, RevealSecret: true})
	if err != nil {
		t.Fatalf("create api key: %v", err)
	}
	if key.Result.OneTimeSecret == "" || key.Result.APIKey.SecretSHA256 != "" {
		t.Fatalf("unexpected create key result: %#v", key.Result)
	}
	listed, err := repository.ListAPIKeys(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID)
	if err != nil {
		t.Fatalf("list api keys: %v", err)
	}
	if listed.Result.Count == 0 || listed.Result.APIKeys[0].SecretSHA256 != "" {
		t.Fatalf("unexpected list result: %#v", listed.Result)
	}
	verified, err := repository.VerifyAPIKeySecret(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "key_live_submit", key.Result.OneTimeSecret, ashrclone.ScopeRunSubmit)
	if err != nil {
		t.Fatalf("verify api key: %v", err)
	}
	if !verified.Result.Authenticated || verified.Result.SecretValuePresent {
		t.Fatalf("unexpected verify result: %#v", verified.Result)
	}
	if _, err := repository.PreflightAPIKey(ashrclone.PreflightOptions{TenantID: boot.Result.Tenant.TenantID, ProjectID: boot.Result.Project.ProjectID, KeyID: "key_live_submit", Scope: ashrclone.ScopeRunUpload, Operation: "upload_run"}); err == nil {
		t.Fatal("expected scope denial before mutation")
	}
	if _, err := repository.ConfigureAPIKeyRateLimit(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "key_live_submit", "sdk_submit", 1); err != nil {
		t.Fatalf("configure rate limit: %v", err)
	}
	if _, err := repository.PreflightAPIKey(ashrclone.PreflightOptions{TenantID: boot.Result.Tenant.TenantID, ProjectID: boot.Result.Project.ProjectID, KeyID: "key_live_submit", Scope: ashrclone.ScopeRunSubmit, Operation: "sdk_submit"}); err != nil {
		t.Fatalf("preflight submit: %v", err)
	}
	if _, err := repository.SubmitRun(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, boot.Result.Dataset.DatasetID, "agent:live", "run_live_key", nil, ashrclone.IdempotencyOptions{Key: "idem_live_key", APIKeyID: "key_live_submit"}); err != nil {
		t.Fatalf("submit run: %v", err)
	}
	if _, err := repository.PreflightAPIKey(ashrclone.PreflightOptions{TenantID: boot.Result.Tenant.TenantID, ProjectID: boot.Result.Project.ProjectID, KeyID: "key_live_submit", Scope: ashrclone.ScopeRunSubmit, Operation: "sdk_submit"}); err == nil {
		t.Fatal("expected rate limit denial after one submit")
	}
	snapshot, err := repository.APIKeyRateLimitSnapshot(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "key_live_submit")
	if err != nil {
		t.Fatalf("rate limit snapshot: %v", err)
	}
	if snapshot.Result.Count != 1 || snapshot.Result.RateLimits[0].Used != 1 || snapshot.Result.RateLimits[0].Remaining != 0 {
		t.Fatalf("unexpected rate limit snapshot: %#v", snapshot.Result)
	}
	revoked, err := repository.RevokeAPIKey(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, "key_live_submit")
	if err != nil {
		t.Fatalf("revoke api key: %v", err)
	}
	if !revoked.Result.Revoked || revoked.Result.SecretSHA256 != "" {
		t.Fatalf("unexpected revoke result: %#v", revoked.Result)
	}
	if _, err := repository.PreflightAPIKey(ashrclone.PreflightOptions{TenantID: boot.Result.Tenant.TenantID, ProjectID: boot.Result.Project.ProjectID, KeyID: "key_live_submit", Scope: ashrclone.ScopeRunSubmit, Operation: "sdk_submit"}); err == nil {
		t.Fatal("expected revoked key denial")
	}
}
