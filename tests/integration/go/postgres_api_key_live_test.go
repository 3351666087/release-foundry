package gointegration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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

func TestPostgresHTTPAPIKeyLifecycleLiveOptIn(t *testing.T) {
	dsn := os.Getenv("A1_POSTGRES_TEST_DSN")
	if dsn == "" {
		t.Skip("set A1_POSTGRES_TEST_DSN to run live Postgres HTTP API key proof")
	}
	repository, err := ashrclone.OpenPostgresRepository(dsn)
	if err != nil {
		t.Fatalf("open postgres repository: %v", err)
	}
	defer repository.Close()
	if err := repository.Migrate(context.Background()); err != nil {
		t.Fatalf("migrate postgres repository: %v", err)
	}
	server := httptest.NewServer(ashrclone.NewHTTPHandler(repository))
	defer server.Close()

	boot := postLiveJSON[ashrclone.BootstrapResult](t, server.URL+"/bootstrap", ashrclone.JSONMap{
		"tenant_name": "Tenant", "project_name": "HTTP Keys", "tenant_id": "tenant_http_live", "project_id": "project_http_live", "dataset_id": "dataset_http_live", "dataset_name": "Dataset",
	})
	created := postLiveJSON[ashrclone.APIKeyCreateResult](t, server.URL+"/v1/projects/project_http_live/api-keys", ashrclone.JSONMap{
		"tenant_id": "tenant_http_live", "key_id": "key_http_live", "name": "HTTP live", "scopes": []string{ashrclone.ScopeRunSubmit, ashrclone.ScopeUsageRead, ashrclone.ScopeAPIKeyWrite}, "reveal_secret": true,
	})
	if created.OneTimeSecret == "" || created.APIKey.SecretSHA256 != "" {
		t.Fatalf("unexpected key create result: %#v", created)
	}
	verified := postLiveJSON[ashrclone.APIKeyVerifyResult](t, server.URL+"/v1/projects/project_http_live/api-keys/key_http_live/verify", ashrclone.JSONMap{
		"tenant_id": "tenant_http_live", "secret": created.OneTimeSecret, "scope": ashrclone.ScopeRunSubmit,
	})
	if !verified.Authenticated || verified.SecretValuePresent {
		t.Fatalf("unexpected verify result: %#v", verified)
	}
	postLiveJSONWithHeaders[ashrclone.APIKeyRateLimit](t, server.URL+"/v1/projects/project_http_live/api-keys/key_http_live/rate-limit", ashrclone.JSONMap{
		"tenant_id": "tenant_http_live", "operation": "sdk_submit", "limit": 1,
	}, map[string]string{"Authorization": "Bearer " + created.OneTimeSecret})
	submitted := postLiveJSONWithHeaders[ashrclone.Run](t, server.URL+"/v1/projects/project_http_live/sdk-submit", ashrclone.JSONMap{
		"tenant_id": "tenant_http_live", "dataset_id": boot.Dataset.DatasetID, "agent_ref": "agent:http", "run_id": "run_http_live", "idempotency_key": "idem_http_live",
	}, map[string]string{"Authorization": "Bearer " + created.OneTimeSecret})
	if submitted.RunID != "run_http_live" || submitted.Status != "queued" {
		t.Fatalf("unexpected bearer submit: %#v", submitted)
	}
	quota := postLiveErrorWithHeaders(t, server.URL+"/v1/projects/project_http_live/sdk-submit", ashrclone.JSONMap{
		"tenant_id": "tenant_http_live", "dataset_id": boot.Dataset.DatasetID, "agent_ref": "agent:http", "run_id": "run_http_live_2", "idempotency_key": "idem_http_live_2",
	}, map[string]string{"Authorization": "Bearer " + created.OneTimeSecret}, http.StatusTooManyRequests)
	if quota.Code != "quota_exceeded" || quota.Limit != 1 || quota.Used != 1 || quota.Remaining != 0 {
		t.Fatalf("unexpected quota error: %#v", quota)
	}
	usage := getLiveJSONWithHeaders[ashrclone.UsageSnapshot](t, server.URL+"/v1/projects/project_http_live/usage?tenant_id=tenant_http_live", map[string]string{"Authorization": "Bearer " + created.OneTimeSecret})
	if operationTotalEvents(usage.OperationTotals, "sdk.submit") != 1 {
		t.Fatalf("quota denial caused side effects, usage=%#v", usage.OperationTotals)
	}
	revoked := postLiveJSONWithHeaders[ashrclone.APIKeyRecord](t, server.URL+"/v1/projects/project_http_live/api-keys/key_http_live/revoke", ashrclone.JSONMap{"tenant_id": "tenant_http_live"}, map[string]string{"Authorization": "Bearer " + created.OneTimeSecret})
	if !revoked.Revoked || revoked.SecretSHA256 != "" {
		t.Fatalf("unexpected revoke result: %#v", revoked)
	}
	revokedError := postLiveErrorWithHeaders(t, server.URL+"/v1/projects/project_http_live/sdk-submit", ashrclone.JSONMap{
		"tenant_id": "tenant_http_live", "dataset_id": boot.Dataset.DatasetID, "agent_ref": "agent:http", "run_id": "run_http_live_3", "idempotency_key": "idem_http_live_3",
	}, map[string]string{"Authorization": "Bearer " + created.OneTimeSecret}, http.StatusUnauthorized)
	if revokedError.Code != "authentication_failed" {
		t.Fatalf("unexpected revoked error: %#v", revokedError)
	}
}

func getLiveJSONWithHeaders[T any](t *testing.T, url string, headers map[string]string) T {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		t.Fatal(err)
	}
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		var failure ashrclone.JSONMap
		_ = json.NewDecoder(resp.Body).Decode(&failure)
		t.Fatalf("status=%d body=%#v", resp.StatusCode, failure)
	}
	var result T
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		t.Fatal(err)
	}
	return result
}
func postLiveJSON[T any](t *testing.T, url string, body ashrclone.JSONMap) T {
	t.Helper()
	return postLiveJSONWithHeaders[T](t, url, body, nil)
}

func postLiveJSONWithHeaders[T any](t *testing.T, url string, body ashrclone.JSONMap, headers map[string]string) T {
	t.Helper()
	encoded, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(encoded))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		var failure ashrclone.JSONMap
		_ = json.NewDecoder(resp.Body).Decode(&failure)
		t.Fatalf("status=%d body=%#v", resp.StatusCode, failure)
	}
	var result T
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		t.Fatal(err)
	}
	return result
}

func operationTotalEvents(totals []ashrclone.UsageOperationTotal, operation string) int {
	for _, total := range totals {
		if total.Operation == operation {
			return total.Events
		}
	}
	return 0
}

type liveError struct {
	Code      string `json:"code"`
	Limit     int    `json:"limit"`
	Used      int    `json:"used"`
	Remaining int    `json:"remaining"`
}

func postLiveError(t *testing.T, url string, body ashrclone.JSONMap) liveError {
	t.Helper()
	return postLiveErrorWithHeaders(t, url, body, nil, http.StatusTooManyRequests)
}

func postLiveErrorWithHeaders(t *testing.T, url string, body ashrclone.JSONMap, headers map[string]string, wantStatus int) liveError {
	t.Helper()
	encoded, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(encoded))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != wantStatus {
		t.Fatalf("expected %d, got %d", wantStatus, resp.StatusCode)
	}
	var envelope struct {
		Error liveError `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&envelope); err != nil {
		t.Fatal(err)
	}
	return envelope.Error
}
