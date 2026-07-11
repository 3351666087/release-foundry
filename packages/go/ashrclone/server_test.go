package ashrclone

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
)

func TestHTTPHandlerHealth(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()

	resp, err := http.Get(server.URL + "/health")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d", resp.StatusCode)
	}
	var body JSONMap
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body["status"] != "ok" || body["schema_version"] != ControlPlaneSchemaVersion {
		t.Fatalf("unexpected health body: %#v", body)
	}
}

func TestHTTPHandlerHealthReportsExplicitBackendReadiness(t *testing.T) {
	server := httptest.NewServer(NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{BackendName: "postgres_repository_v0", BackendReady: false}))
	defer server.Close()

	resp, err := http.Get(server.URL + "/healthz")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var body JSONMap
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body["backend"] != "postgres_repository_v0" || body["backend_ready"] != false || body["backend_mode"] != "postgres" {
		t.Fatalf("unexpected backend health fields: %#v", body)
	}
}
func TestHTTPHandlerBootstrapAndSubmit(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()

	boot := postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name":  "Tenant",
		"project_name": "Project",
		"tenant_id":    "tenant_http",
		"project_id":   "project_http",
		"dataset_id":   "dataset_http",
		"dataset_name": "Dataset",
	})
	if boot.Dataset.DatasetID != "dataset_http" || boot.Project.ProjectID != "project_http" {
		t.Fatalf("unexpected bootstrap response: %#v", boot)
	}

	client := NewClient(WithBaseURL(server.URL), WithRetry(0, 0))
	submit, err := client.SubmitRunHTTP(context.Background(), "tenant_http", "project_http", SubmitRunOptions{DatasetID: "dataset_http", AgentRef: "agent:http", RunID: "run_http", APIKeyID: "key_http", IdempotencyKey: "idem_submit"})
	if err != nil {
		t.Fatal(err)
	}
	if submit.Operation != "sdk_submit" || submit.Result["run_id"] != "run_http" || submit.Result["status"] != "queued" {
		t.Fatalf("unexpected submit response: %#v", submit)
	}
}

func TestHTTPHandlerWorkerJobLifecycle(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Workers", "tenant_id": "tenant_workers", "project_id": "project_workers", "dataset_name": "Dataset",
	})

	client := NewClient(WithBaseURL(server.URL), WithRetry(0, 0))
	enqueued, err := client.EnqueueWorkerJobHTTP(context.Background(), "tenant_workers", "project_workers", JSONMap{"gate": "candidate"}, EnqueueWorkerJobHTTPOptions{JobType: "release_gate", TargetID: "run_workers", JobID: "job_workers", MaxAttempts: 2, APIKeyID: "key_workers", IdempotencyKey: "idem_workers"})
	if err != nil {
		t.Fatal(err)
	}
	if enqueued.Operation != "worker.job.enqueue" || enqueued.Result["job_id"] != "job_workers" {
		t.Fatalf("unexpected enqueue response: %#v", enqueued)
	}

	leased, err := client.LeaseWorkerJobHTTP(context.Background(), "tenant_workers", "project_workers", LeaseWorkerJobHTTPOptions{LeaseOwnerID: "worker_1", JobType: "release_gate", APIKeyID: "key_workers"})
	if err != nil {
		t.Fatal(err)
	}
	if leased.Operation != "worker.job.lease" || leased.Result["leased"] != true {
		t.Fatalf("unexpected lease response: %#v", leased)
	}

	completed, err := client.CompleteWorkerJobHTTP(context.Background(), "tenant_workers", "project_workers", "job_workers", JSONMap{"status": "ok"}, WorkerJobLeaseActionHTTPOptions{LeaseOwnerID: "worker_1", APIKeyID: "key_workers"})
	if err != nil {
		t.Fatal(err)
	}
	if completed.Operation != "worker.job.complete" || completed.Result["status"] != WorkerJobStatusCompleted {
		t.Fatalf("unexpected complete response: %#v", completed)
	}

	listed, err := client.ListWorkerJobsHTTP(context.Background(), "tenant_workers", "project_workers", ListWorkerJobsHTTPOptions{Status: WorkerJobStatusCompleted, AuthKeyID: "key_workers"})
	if err != nil {
		t.Fatal(err)
	}
	if listed.Operation != "worker.job.list" || listed.Result["count"].(float64) != 1 {
		t.Fatalf("unexpected list response: %#v", listed)
	}
}

func TestHTTPHandlerRunUploadTraceAndArtifactManifests(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Runs", "tenant_id": "tenant_runs", "project_id": "project_runs", "dataset_id": "dataset_runs", "dataset_name": "Dataset",
	})
	adminKey := postJSONForTest[APIKeyCreateResult](t, server.URL+"/v1/projects/project_runs/api-keys", JSONMap{
		"tenant_id": "tenant_runs", "key_id": "key_runs_admin", "name": "admin-key", "scopes": []string{ScopeAPIKeyWrite, ScopeAPIKeyRead}, "reveal_secret": true,
	})
	postJSONWithHeadersForTest[APIKeyCreateResult](t, server.URL+"/v1/projects/project_runs/api-keys", JSONMap{
		"tenant_id": "tenant_runs", "key_id": "key_runs", "name": "full-run-key", "scopes": []string{ScopeRunSubmit, ScopeRunUpload, ScopeTraceIngest, ScopeArtifactManifestWrite, ScopeArtifactManifestRead, ScopeRunLifecycleRead, ScopeAuditRead, ScopeEvidenceRead},
	}, map[string]string{"Authorization": "Bearer " + adminKey.OneTimeSecret})
	postJSONWithHeadersForTest[APIKeyCreateResult](t, server.URL+"/v1/projects/project_runs/api-keys", JSONMap{
		"tenant_id": "tenant_runs", "key_id": "key_runs_no_evidence", "name": "audit-only-key", "scopes": []string{ScopeAuditRead},
	}, map[string]string{"Authorization": "Bearer " + adminKey.OneTimeSecret})

	client := NewClient(WithBaseURL(server.URL), WithRetry(0, 0))
	if _, err := client.SubmitRunHTTP(context.Background(), "tenant_runs", "project_runs", SubmitRunOptions{DatasetID: "dataset_runs", AgentRef: "agent:runs", RunID: "run_routes", APIKeyID: "key_runs", IdempotencyKey: "idem_run_routes"}); err != nil {
		t.Fatal(err)
	}

	upload, err := client.UploadRunHTTP(context.Background(), "tenant_runs", "project_runs", "run_routes", JSONMap{"score": 0.97, "status": "passed"}, UploadRunOptions{UploadID: "upload_routes", APIKeyID: "key_runs", IdempotencyKey: "idem_upload_routes"})
	if err != nil {
		t.Fatal(err)
	}
	if upload.Operation != "upload_run" || upload.Result["upload_id"] != "upload_routes" || upload.Result["raw_payload_included"] != false || upload.Result["result_sha256"] == "" {
		t.Fatalf("unexpected upload response: %#v", upload)
	}

	trace, err := client.IngestTraceHTTP(context.Background(), "tenant_runs", "project_runs", "run_routes", []JSONMap{{"span_id": "span_1", "latency_ms": 12}, {"span_id": "span_2", "status": "ok"}}, IngestTraceOptions{BatchID: "trace_routes", APIKeyID: "key_runs", IdempotencyKey: "idem_trace_routes"})
	if err != nil {
		t.Fatal(err)
	}
	if trace.Operation != "ingest_trace" || trace.Result["batch_id"] != "trace_routes" || trace.Result["observation_count"].(float64) != 2 || trace.Result["observations_sha256"] == "" {
		t.Fatalf("unexpected trace response: %#v", trace)
	}

	manifest, err := client.CreateArtifactManifestHTTP(context.Background(), "tenant_runs", "project_runs", "run_routes", JSONMap{"artifacts": []any{JSONMap{"path": "reports/run.json", "sha256": "abc123"}}}, ArtifactManifestOptions{ArtifactID: "artifact_routes", APIKeyID: "key_runs", IdempotencyKey: "idem_artifact_routes"})
	if err != nil {
		t.Fatal(err)
	}
	if manifest.Operation != "artifact_manifest" || manifest.Result["artifact_id"] != "artifact_routes" || manifest.Result["manifest_sha256"] == "" {
		t.Fatalf("unexpected artifact response: %#v", manifest)
	}

	listed, err := client.ListArtifactManifestsHTTP(context.Background(), "tenant_runs", "project_runs", "run_routes", AuthKeyOptions{AuthKeyID: "key_runs"})
	if err != nil {
		t.Fatal(err)
	}
	if listed.Operation != "artifact_manifests" || listed.Result["count"].(float64) != 1 {
		t.Fatalf("unexpected artifact list response: %#v", listed)
	}

	lifecycle, err := client.LifecycleHTTP(context.Background(), "tenant_runs", "project_runs", "run_routes", AuthKeyOptions{AuthKeyID: "key_runs"})
	if err != nil {
		t.Fatal(err)
	}
	counts, ok := lifecycle.Result["counts"].(map[string]any)
	if !ok {
		t.Fatalf("lifecycle counts missing: %#v", lifecycle)
	}
	run, ok := lifecycle.Result["run"].(map[string]any)
	if !ok {
		t.Fatalf("lifecycle run missing: %#v", lifecycle)
	}
	if lifecycle.Operation != "lifecycle" || lifecycle.Result["run_id"] != "run_routes" || run["status"] != "uploaded" || counts["uploads"].(float64) != 1 || counts["trace_batches"].(float64) != 1 || counts["artifacts"].(float64) != 1 {
		t.Fatalf("unexpected lifecycle response: %#v", lifecycle)
	}
	uploadRows, ok := lifecycle.Result["uploads"].([]any)
	if !ok || len(uploadRows) != 1 {
		t.Fatalf("unexpected lifecycle uploads: %#v", lifecycle.Result["uploads"])
	}
	uploadRow, ok := uploadRows[0].(map[string]any)
	if !ok || uploadRow["result_sha256"] == "" || uploadRow["raw_payload_included"] != false {
		t.Fatalf("unexpected lifecycle uploads: %#v", lifecycle.Result["uploads"])
	}

	audit, err := client.AuditLogHTTP(context.Background(), "tenant_runs", "project_runs", AuditLogOptions{RunID: "run_routes", AuthKeyID: "key_runs", Limit: 3})
	if err != nil {
		t.Fatal(err)
	}
	if audit.Operation != "audit_log" || audit.Result["count"].(float64) == 0 || audit.Result["run_id"] != "run_routes" {
		t.Fatalf("unexpected audit log response: %#v", audit)
	}

	packet, err := client.BuildReleaseEvidencePacketHTTP(context.Background(), "tenant_runs", "project_runs", "run_routes", AuthKeyOptions{AuthKeyID: "key_runs"})
	if err != nil {
		t.Fatal(err)
	}
	if packet.Operation != "release_evidence" || packet.Result["packet_id"] == "" || packet.Result["packet_sha256"] == "" {
		t.Fatalf("unexpected release evidence response: %#v", packet)
	}

	packetMap, ok := packet.Result["packet"].(JSONMap)
	if !ok {
		packetMap = packet.Result
	}
	verified, err := client.VerifyReleaseEvidencePacketHTTP(context.Background(), "tenant_runs", "project_runs", "run_routes", VerifyReleaseEvidencePacketOptions{AuthKeyID: "key_runs", Packet: packetMap})
	if err != nil {
		t.Fatal(err)
	}
	if verified.Operation != "release_evidence_verify" || verified.Result["verified"] != true {
		t.Fatalf("unexpected release evidence verification response: %#v", verified)
	}

	assertControlPlaneError(t, requestForTest(t, http.MethodGet, server.URL+"/v1/projects/project_runs/runs/run_routes/release-evidence?tenant_id=tenant_runs&auth_key_id=key_runs_no_evidence", nil), http.StatusForbidden, "scope_denied")
}

func TestHTTPHandlerRunRoutesRejectInlineMedia(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Safe", "tenant_id": "tenant_safe", "project_id": "project_safe", "dataset_id": "dataset_safe", "dataset_name": "Dataset",
	})
	client := NewClient(WithBaseURL(server.URL), WithRetry(0, 0))
	if _, err := client.SubmitRunHTTP(context.Background(), "tenant_safe", "project_safe", SubmitRunOptions{DatasetID: "dataset_safe", AgentRef: "agent:safe", RunID: "run_safe", APIKeyID: "key_safe", IdempotencyKey: "idem_safe"}); err != nil {
		t.Fatal(err)
	}

	_, err := client.UploadRunHTTP(context.Background(), "tenant_safe", "project_safe", "run_safe", JSONMap{"data_url": "data:image/png;base64,AAAA"}, UploadRunOptions{APIKeyID: "key_safe", IdempotencyKey: "idem_unsafe"})
	if err == nil {
		t.Fatal("expected inline media rejection")
	}
}

func TestHTTPHandlerAPIKeyPreflightAndQuota(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Auth", "tenant_id": "tenant_key", "project_id": "project_key", "dataset_id": "dataset_key", "dataset_name": "Dataset",
	})
	assertControlPlaneError(t, requestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_key/api-keys", JSONMap{
		"tenant_id": "tenant_key", "name": "bad", "scopes": []string{ScopeRunSubmit}, "api_key": "sk-test-never-read",
	}), http.StatusBadRequest, "secret_input_rejected")

	created := postJSONForTest[APIKeyCreateResult](t, server.URL+"/v1/projects/project_key/api-keys", JSONMap{
		"tenant_id": "tenant_key", "key_id": "key_http_lifecycle", "name": "submitter", "scopes": []string{ScopeRunSubmit, ScopeAPIKeyWrite, ScopeAPIKeyPreflight}, "reveal_secret": true,
	})
	if created.OneTimeSecret == "" || created.APIKey.SecretSHA256 != "" {
		t.Fatalf("unexpected key create response: %#v", created)
	}

	verified := postJSONForTest[APIKeyVerifyResult](t, server.URL+"/v1/projects/project_key/api-keys/key_http_lifecycle/verify", JSONMap{
		"tenant_id": "tenant_key", "secret": created.OneTimeSecret, "scope": ScopeRunSubmit,
	})
	if !verified.Authenticated {
		t.Fatalf("expected test secret to verify: %#v", verified)
	}

	preflightDenied := requestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_key/api-keys/preflight", JSONMap{
		"tenant_id": "tenant_key", "key_id": "key_http_lifecycle", "scope": ScopeRunUpload, "operation": "upload_run",
	})
	preflightDenied.Header.Set("Authorization", "Bearer "+created.OneTimeSecret)
	assertControlPlaneError(t, preflightDenied, http.StatusForbidden, "scope_denied")

	postJSONWithHeadersForTest[APIKeyRateLimit](t, server.URL+"/v1/projects/project_key/api-keys/key_http_lifecycle/rate-limit", JSONMap{
		"tenant_id": "tenant_key", "operation": "sdk_submit", "limit": 1,
	}, map[string]string{"Authorization": "Bearer " + created.OneTimeSecret})
	client := NewClient(WithBaseURL(server.URL), WithRetry(0, 0))
	if _, err := client.SubmitRunHTTP(context.Background(), "tenant_key", "project_key", SubmitRunOptions{DatasetID: "dataset_key", AgentRef: "agent:key", RunID: "run_key", APIKeyID: "key_http_lifecycle", IdempotencyKey: "idem_key"}); err != nil {
		t.Fatal(err)
	}
	quotaResp := assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_key/sdk-submit", JSONMap{
		"tenant_id": "tenant_key", "dataset_id": "dataset_key", "agent_ref": "agent:key", "run_id": "run_key_2", "api_key_id": "key_http_lifecycle", "idempotency_key": "idem_key_2",
	}, "tenant_key", "key_http_lifecycle"), http.StatusTooManyRequests, "quota_exceeded")
	if quotaResp.Error.Operation != usageOperationSubmit || quotaResp.Error.Meter != QuotaMeterRuns || quotaResp.Error.Limit != 1 || quotaResp.Error.Used != 1 || quotaResp.Error.Requested != 1 || quotaResp.Error.Remaining != 0 {
		t.Fatalf("unexpected quota error detail: %#v", quotaResp.Error)
	}
}

func TestHTTPHandlerRouteManifestIncludesRunFamilies(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()

	resp, err := http.Get(server.URL + "/openapi.json")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var body struct {
		Routes         []string             `json:"routes"`
		RouteManifest  []RouteManifestEntry `json:"route_manifest"`
		RouteScopeDocs RouteScopeDocs       `json:"route_scope_docs"`
		ScopeManifest  map[string][]struct {
			Route     string `json:"route"`
			Operation string `json:"operation"`
		} `json:"scope_manifest"`
		RawPayloadsIncluded bool `json:"raw_payloads_included"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.RawPayloadsIncluded {
		t.Fatal("route manifest must not claim raw payloads are included")
	}
	if !sort.StringsAreSorted(body.Routes) {
		t.Fatalf("routes are not deterministic: %#v", body.Routes)
	}
	if len(body.Routes) != len(body.RouteManifest) {
		t.Fatalf("routes length = %d, route manifest length = %d", len(body.Routes), len(body.RouteManifest))
	}
	want := map[string]bool{
		"GET /v1/projects/{project_id}/usage":                             false,
		"POST /v1/projects/{project_id}/usage/quotas":                     false,
		"POST /v1/projects/{project_id}/quota/limits":                     false,
		"POST /v1/projects/{project_id}/billing/checkout-plan":            false,
		"POST /v1/projects/{project_id}/billing/portal-plan":              false,
		"POST /v1/projects/{project_id}/billing/webhooks/ingest":          false,
		"GET /v1/projects/{project_id}/billing/ledger":                    false,
		"GET /v1/projects/{project_id}/audit-chain/verify":                false,
		"POST /v1/projects/{project_id}/audit-chain/verify":               false,
		"POST /v1/projects/{project_id}/runs/{run_id}/upload":             false,
		"POST /v1/projects/{project_id}/runs/{run_id}/trace-events":       false,
		"POST /v1/projects/{project_id}/runs/{run_id}/artifact-manifests": false,
		"GET /v1/projects/{project_id}/runs/{run_id}/artifact-manifests":  false,
	}
	for _, route := range body.Routes {
		if _, ok := want[route]; ok {
			want[route] = true
		}
	}
	for route, found := range want {
		if !found {
			t.Fatalf("manifest missing %s in %#v", route, body.Routes)
		}
	}
	byRoute := map[string]RouteManifestEntry{}
	for _, route := range body.RouteManifest {
		if route.Route != route.Method+" "+route.Path {
			t.Fatalf("route %q does not match method/path %#v", route.Route, route)
		}
		if !route.PublicSafe {
			t.Fatalf("route metadata is not public-safe: %#v", route)
		}
		if strings.Contains(route.Path, "project_key") || strings.Contains(route.Path, "run_key") {
			t.Fatalf("route path includes concrete fixture identifier: %#v", route)
		}
		byRoute[route.Route] = route
	}
	if got := byRoute["POST /v1/projects/{project_id}/runs/{run_id}/upload"].Scopes; len(got) != 1 || got[0] != ScopeRunUpload {
		t.Fatalf("upload scope = %#v, want %s", got, ScopeRunUpload)
	}
	if got := byRoute["GET /v1/projects/{project_id}/worker-jobs"].Scopes; len(got) != 1 || got[0] != ScopeWorkerJobList {
		t.Fatalf("worker list scope = %#v, want %s", got, ScopeWorkerJobList)
	}
	if got := byRoute["POST /v1/projects/{project_id}/billing/checkout-plan"].Scopes; len(got) != 1 || got[0] != ScopeBillingWrite {
		t.Fatalf("billing checkout scope = %#v, want %s", got, ScopeBillingWrite)
	}
	if got := byRoute["GET /v1/projects/{project_id}/billing/ledger"].Scopes; len(got) != 1 || got[0] != ScopeBillingRead {
		t.Fatalf("billing ledger scope = %#v, want %s", got, ScopeBillingRead)
	}
	if got := byRoute["POST /v1/projects/{project_id}/billing/webhooks/ingest"].Scopes; len(got) != 1 || got[0] != ScopeBillingWebhookIngest {
		t.Fatalf("billing webhook scope = %#v, want %s", got, ScopeBillingWebhookIngest)
	}
	if !byRoute["POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat"].AuthRequired {
		t.Fatal("worker heartbeat requires an authenticated handle and must be marked auth required")
	}
	if !body.RouteScopeDocs.PublicSafe || body.RouteScopeDocs.RawPayloadsIncluded || body.RouteScopeDocs.Source != "generated_from_go_route_manifest" {
		t.Fatalf("unexpected route scope docs safety metadata: %#v", body.RouteScopeDocs)
	}
	usageDocs := routeScopeDocGroupByName(body.RouteScopeDocs, "usage_quota")
	if usageDocs == nil || !stringSliceContains(usageDocs.Routes, "GET /v1/projects/{project_id}/usage") || !stringSliceContains(usageDocs.Routes, "GET /v1/projects/{project_id}/quota") || !stringSliceContains(usageDocs.Scopes, ScopeUsageRead) {
		t.Fatalf("usage quota docs did not export manifest-derived routes/scopes: %#v", usageDocs)
	}
	billingDocs := routeScopeDocGroupByName(body.RouteScopeDocs, "billing_contract")
	if billingDocs == nil || !stringSliceContains(billingDocs.Routes, "POST /v1/projects/{project_id}/billing/checkout-plan") || !stringSliceContains(billingDocs.Routes, "GET /v1/projects/{project_id}/billing/ledger") || !stringSliceContains(billingDocs.Scopes, ScopeBillingRead) || !stringSliceContains(billingDocs.Scopes, ScopeBillingWrite) || !stringSliceContains(billingDocs.Scopes, ScopeBillingWebhookIngest) {
		t.Fatalf("billing docs did not export manifest-derived routes/scopes: %#v", billingDocs)
	}
	lifecycleDocs := routeScopeDocGroupByName(body.RouteScopeDocs, "run_lifecycle")
	if lifecycleDocs == nil || !stringSliceContains(lifecycleDocs.Routes, "GET /v1/projects/{project_id}/runs/{run_id}/lifecycle") || !stringSliceContains(lifecycleDocs.Scopes, ScopeRunLifecycleRead) {
		t.Fatalf("lifecycle docs did not export manifest-derived routes/scopes: %#v", lifecycleDocs)
	}
	auditDocs := routeScopeDocGroupByName(body.RouteScopeDocs, "audit")
	if auditDocs == nil || !stringSliceContains(auditDocs.Routes, "GET /v1/projects/{project_id}/audit-log") || !stringSliceContains(auditDocs.Routes, "POST /v1/projects/{project_id}/audit-chain/verify") || !stringSliceContains(auditDocs.Scopes, ScopeAuditRead) {
		t.Fatalf("audit docs did not export manifest-derived routes/scopes: %#v", auditDocs)
	}
	if _, ok := body.ScopeManifest[ScopeRunUpload]; !ok {
		t.Fatalf("scope manifest missing %s", ScopeRunUpload)
	}
	for _, entry := range body.ScopeManifest[ScopeRunUpload] {
		if entry.Route == "POST /v1/projects/{project_id}/runs/{run_id}/upload" {
			return
		}
	}
	t.Fatalf("scope manifest did not map %s to upload route: %#v", ScopeRunUpload, body.ScopeManifest[ScopeRunUpload])
}

func TestGoRouteScopeDocsIncludePublicPlanLimits(t *testing.T) {
	docs := GoRouteScopeDocs(GoRouteManifestEntries())
	if docs.SchemaVersion != "ashr.clone.go_route_scope_docs.v1" || !docs.PublicSafe || docs.RawPayloadsIncluded {
		t.Fatalf("unexpected route scope docs metadata: %#v", docs)
	}
	if got := len(docs.RouteGroups); got != 4 {
		t.Fatalf("route group count = %d, want usage/billing/lifecycle/audit", got)
	}
	usageDocs := routeScopeDocGroupByName(docs, "usage_quota")
	if usageDocs == nil || !stringSliceContains(usageDocs.Routes, "GET /v1/projects/{project_id}/usage") || !stringSliceContains(usageDocs.Scopes, ScopeUsageRead) {
		t.Fatalf("usage docs missing manifest-derived route or scope: %#v", usageDocs)
	}
	billingDocs := routeScopeDocGroupByName(docs, "billing_contract")
	if billingDocs == nil || !stringSliceContains(billingDocs.Routes, "POST /v1/projects/{project_id}/billing/webhooks/ingest") || !stringSliceContains(billingDocs.Scopes, ScopeBillingWebhookIngest) {
		t.Fatalf("billing docs missing manifest-derived route or scope: %#v", billingDocs)
	}
	startup := routeScopeDocPlanByName(docs, "Startup")
	developer := routeScopeDocPlanByName(docs, "Developer")
	if developer == nil || startup == nil {
		t.Fatalf("missing public plan references: %#v", docs.PlanLimits)
	}
	assertRouteScopePlanLimit(t, developer, "graded_scenarios", 5000, "scenario")
	assertRouteScopePlanLimit(t, developer, "observations", 250000, "observation")
	assertRouteScopePlanLimit(t, developer, "voice_minutes", 1000, "minute")
	assertRouteScopePlanLimit(t, developer, "projects", 1, "project")
	assertRouteScopePlanLimit(t, startup, "graded_scenarios", 100000, "scenario")
	assertRouteScopePlanLimit(t, startup, "observations", 10000000, "observation")
	assertRouteScopePlanLimit(t, startup, "voice_minutes", 50000, "minute")
	assertRouteScopePlanLimit(t, startup, "projects", 0, "unlimited")
	metricNames := []string{}
	for _, metric := range docs.PlanMetrics {
		metricNames = append(metricNames, metric.Metric)
	}
	for _, want := range []string{"graded_scenarios", "observations", "voice_minutes", "projects"} {
		if !stringSliceContains(metricNames, want) {
			t.Fatalf("route scope docs missing plan metric %q: %#v", want, docs.PlanMetrics)
		}
	}
	encoded, err := json.Marshal(docs)
	if err != nil {
		t.Fatal(err)
	}
	for _, secretish := range []string{"tenant_", "project_contract", "key_contract", "sk-"} {
		if strings.Contains(string(encoded), secretish) {
			t.Fatalf("route scope docs contain fixture/secret-like value %q: %s", secretish, encoded)
		}
	}
}

func TestGoRouteScopeDocsArtifactMatchesGeneratedPublicExport(t *testing.T) {
	artifactPath := filepath.Join("..", "..", "..", "docs", "a1", "evidence", "go_route_scope_docs.json")
	content, err := os.ReadFile(artifactPath)
	if err != nil {
		t.Fatal(err)
	}
	var artifact struct {
		SchemaVersion       string         `json:"schema_version"`
		ArtifactID          string         `json:"artifact_id"`
		Owner               string         `json:"owner"`
		PublicSafe          bool           `json:"public_safe"`
		RawPayloadsIncluded bool           `json:"raw_payloads_included"`
		SourcePolicy        JSONMap        `json:"source_policy"`
		Producer            JSONMap        `json:"producer"`
		RouteScopeDocs      RouteScopeDocs `json:"route_scope_docs"`
	}
	if err := json.Unmarshal(content, &artifact); err != nil {
		t.Fatal(err)
	}
	if artifact.SchemaVersion != "ashr.clone.go_route_scope_docs_artifact.v1" || artifact.ArtifactID != "go_route_scope_docs" || artifact.Owner != "a1.go" {
		t.Fatalf("unexpected route scope docs artifact identity: %#v", artifact)
	}
	if !artifact.PublicSafe || artifact.RawPayloadsIncluded {
		t.Fatalf("artifact safety metadata is not public-safe: %#v", artifact)
	}
	if artifact.SourcePolicy["private_evidence_read"] != false || artifact.SourcePolicy["tokens_included"] != false || artifact.SourcePolicy["raw_payloads_included"] != false {
		t.Fatalf("artifact source policy is not public-safe: %#v", artifact.SourcePolicy)
	}
	want := GoRouteScopeDocs(GoRouteManifestEntries())
	legacyWant := routeScopeDocsWithoutGroup(want, "billing_contract")
	if !reflect.DeepEqual(artifact.RouteScopeDocs, want) && !reflect.DeepEqual(artifact.RouteScopeDocs, legacyWant) {
		gotJSON, _ := json.MarshalIndent(artifact.RouteScopeDocs, "", "  ")
		wantJSON, _ := json.MarshalIndent(want, "", "  ")
		t.Fatalf("route scope docs artifact drifted from Go generator\ngot: %s\nwant: %s", gotJSON, wantJSON)
	}
	encoded := string(content)
	for _, secretish := range []string{"tenant_", "project_contract", "key_contract", "Bearer ", "ASHR_API_KEY", "sk-", "raw_request_payload", "raw_response_payload"} {
		if strings.Contains(encoded, secretish) {
			t.Fatalf("route scope docs artifact contains fixture/secret-like value %q", secretish)
		}
	}
}

func TestGoRouteManifestEntriesAreDeterministicAndPublicSafe(t *testing.T) {
	manifest := GoRouteManifestEntries()
	routes := GoRouteManifestRoutes(manifest)
	if !sort.StringsAreSorted(routes) {
		t.Fatalf("route strings are not sorted: %#v", routes)
	}
	if len(routes) != len(manifest) {
		t.Fatalf("routes length = %d, manifest length = %d", len(routes), len(manifest))
	}
	seen := map[string]bool{}
	for i, route := range manifest {
		if route.Route != routes[i] {
			t.Fatalf("manifest route[%d] = %q, route string = %q", i, route.Route, routes[i])
		}
		if seen[route.Route] {
			t.Fatalf("duplicate route %q", route.Route)
		}
		seen[route.Route] = true
		if route.Method == "" || route.Path == "" || route.Category == "" {
			t.Fatalf("route metadata missing public fields: %#v", route)
		}
		if !route.PublicSafe {
			t.Fatalf("route metadata is not public-safe: %#v", route)
		}
		if strings.Contains(route.Path, "tenant_") || strings.Contains(route.Path, "project_contract") || strings.Contains(route.Path, "key_contract") {
			t.Fatalf("route metadata contains fixture values: %#v", route)
		}
	}
	scopes := GoScopeManifest(manifest)
	if _, ok := scopes[ScopeTraceIngest]; !ok {
		t.Fatalf("scope manifest missing %s", ScopeTraceIngest)
	}
	for _, entry := range scopes[ScopeWorkerJobLease] {
		if entry.Route == "POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat" {
			return
		}
	}
	t.Fatalf("scope manifest missing heartbeat route for %s: %#v", ScopeWorkerJobLease, scopes[ScopeWorkerJobLease])
}

func TestHTTPHandlerUsageAndAuditReadEndpoints(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Audit", "tenant_id": "tenant_audit", "project_id": "project_audit", "dataset_id": "dataset_audit", "dataset_name": "Dataset",
	})

	usageResp, err := http.Get(server.URL + "/v1/projects/project_audit/usage?tenant_id=tenant_audit&auth_key_id=key_audit")
	if err != nil {
		t.Fatal(err)
	}
	defer usageResp.Body.Close()
	if usageResp.StatusCode != http.StatusOK {
		t.Fatalf("usage status = %d", usageResp.StatusCode)
	}
	var usage UsageSnapshot
	if err := json.NewDecoder(usageResp.Body).Decode(&usage); err != nil {
		t.Fatal(err)
	}
	if usage.SchemaVersion != ControlPlaneSchemaVersion || usage.TenantID != "tenant_audit" || usage.ProjectID != "project_audit" {
		t.Fatalf("unexpected usage snapshot: %#v", usage)
	}
	quotaResp, err := http.Get(server.URL + "/v1/projects/project_audit/quota?tenant_id=tenant_audit&auth_key_id=key_audit")
	if err != nil {
		t.Fatal(err)
	}
	defer quotaResp.Body.Close()
	if quotaResp.StatusCode != http.StatusOK {
		t.Fatalf("quota status = %d", quotaResp.StatusCode)
	}
	var quota UsageSnapshot
	if err := json.NewDecoder(quotaResp.Body).Decode(&quota); err != nil {
		t.Fatal(err)
	}
	if quota.SchemaVersion != ControlPlaneSchemaVersion || quota.TenantID != "tenant_audit" || quota.ProjectID != "project_audit" {
		t.Fatalf("unexpected quota alias snapshot: %#v", quota)
	}

	auditResp, err := http.Get(server.URL + "/v1/projects/project_audit/audit-chain/verify?tenant_id=tenant_audit&auth_key_id=key_audit")
	if err != nil {
		t.Fatal(err)
	}
	defer auditResp.Body.Close()
	if auditResp.StatusCode != http.StatusOK {
		t.Fatalf("audit status = %d", auditResp.StatusCode)
	}
	var audit AuditChainVerification
	if err := json.NewDecoder(auditResp.Body).Decode(&audit); err != nil {
		t.Fatal(err)
	}
	if audit.SchemaVersion != ControlPlaneSchemaVersion || !audit.Verified || audit.TenantID != "tenant_audit" || audit.ProjectID != "project_audit" {
		t.Fatalf("unexpected audit verification: %#v", audit)
	}
}

func TestHTTPHandlerBillingContractRoutesAreDeterministicAndPublicSafe(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Billing", "tenant_id": "tenant_billing", "project_id": "project_billing", "dataset_id": "dataset_billing", "dataset_name": "Dataset",
	})
	postJSONForTest[APIKeyCreateResult](t, server.URL+"/v1/projects/project_billing/api-keys", JSONMap{
		"tenant_id": "tenant_billing", "key_id": "key_billing", "name": "Billing key", "scopes": []string{ScopeAPIKeyWrite, ScopeBillingRead, ScopeBillingWrite, ScopeBillingWebhookIngest},
	})

	checkout := postJSONForTest[BillingCheckoutPlan](t, server.URL+"/v1/projects/project_billing/billing/checkout-plan", JSONMap{
		"tenant_id": "tenant_billing", "api_key_id": "key_billing", "plan_id": "Startup", "billing_cycle": "annual", "idempotency_key": "idem_checkout", "customer_ref": "cus_public", "success_url": "https://app.example/success", "cancel_url": "https://app.example/cancel", "price": JSONMap{"lookup_key": "startup_usd_monthly", "unit_amount_minor": 9900, "currency": "usd"}, "provider_config": JSONMap{"provider": "Stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF", "raw_secret": "sk_test_synthetic_fixture"}, "metadata": JSONMap{"source": "test", "token": "synthetic-secret-fixture"},
	})
	if checkout.PlanID != "startup" || checkout.BillingCycle != "yearly" || checkout.Provider != "stripe" || checkout.Mode != "test" || !checkout.PublicSafe || checkout.ProviderCalled || checkout.RealChargePossible || checkout.RawPayloadIncluded || checkout.RawSecretsIncluded || checkout.SecretValuePresent || !strings.HasPrefix(checkout.CheckoutURL, "https://billing.local.ashr.invalid/checkout/") {
		t.Fatalf("unexpected checkout contract: %#v", checkout)
	}
	if checkout.CustomerRef != "cus_public" || checkout.SuccessURL != "https://app.example/success" || checkout.CancelURL != "https://app.example/cancel" || checkout.Price["lookup_key"] != "startup_usd_monthly" || checkout.ProviderConfig["secret_ref"] != "env:STRIPE_TEST_REF" || checkout.ProviderConfig["raw_secret"] != Redacted || checkout.ProviderConfig["raw_secret_present"] != false {
		t.Fatalf("checkout semantic fields were not preserved safely: %#v", checkout)
	}
	if checkout.SideEffects["provider_called"] != false || checkout.SideEffects["real_charge_possible"] != false {
		t.Fatalf("checkout side effects were not public-safe: %#v", checkout.SideEffects)
	}
	if checkout.Metadata["token"] != Redacted {
		t.Fatalf("checkout metadata was not redacted: %#v", checkout.Metadata)
	}
	checkoutAgain := postJSONForTest[BillingCheckoutPlan](t, server.URL+"/v1/projects/project_billing/billing/checkout-plan", JSONMap{
		"tenant_id": "tenant_billing", "api_key_id": "key_billing", "plan_id": "startup", "billing_cycle": "yearly", "idempotency_key": "idem_checkout", "customer_ref": "cus_public", "success_url": "https://app.example/success", "cancel_url": "https://app.example/cancel", "price": JSONMap{"lookup_key": "startup_usd_monthly", "unit_amount_minor": 9900, "currency": "usd"}, "provider_config": JSONMap{"provider": "Stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF", "raw_secret": "sk_test_synthetic_fixture"},
	})
	if checkoutAgain.CheckoutID != checkout.CheckoutID || checkoutAgain.CheckoutURL != checkout.CheckoutURL {
		t.Fatalf("checkout route is not deterministic: first=%#v second=%#v", checkout, checkoutAgain)
	}

	portal := postJSONForTest[BillingPortalPlan](t, server.URL+"/v1/projects/project_billing/billing/portal-plan", JSONMap{
		"tenant_id": "tenant_billing", "api_key_id": "key_billing", "plan_id": "developer", "customer_ref": "cus_public", "return_url": "https://app.example/account", "provider_config": JSONMap{"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF"}, "idempotency_key": "idem_portal",
	})
	if portal.PlanID != "developer" || portal.Provider != "stripe" || portal.CustomerRef != "cus_public" || portal.ReturnURL != "https://app.example/account" || portal.ProviderCalled || portal.RealChargePossible || portal.RawPayloadIncluded || portal.RawSecretsIncluded || portal.SecretValuePresent || !strings.HasPrefix(portal.PortalURL, "https://billing.local.ashr.invalid/portal/") {
		t.Fatalf("unexpected portal contract: %#v", portal)
	}

	webhook := postJSONForTest[BillingWebhookIngest](t, server.URL+"/v1/projects/project_billing/billing/webhooks/ingest", JSONMap{
		"tenant_id": "tenant_billing", "api_key_id": "key_billing", "event_type": "subscription.updated", "event_id": "evt_public", "provider": "Stripe", "mode": "test", "plan_id": "Startup", "customer_ref": "cus_public", "status": "Active", "payload_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "signature_header_present": true, "webhook_secret_ref": "env:STRIPE_WEBHOOK_REF", "livemode": false, "metadata": JSONMap{"customer_ref": "cus_public", "card_number": "synthetic-card-fixture", "authorization": "synthetic-auth-fixture"},
	})
	if webhook.EventID != "evt_public" || webhook.Provider != "stripe" || webhook.Mode != "test" || webhook.PlanID != "startup" || webhook.CustomerRef != "cus_public" || webhook.Status != "active" || webhook.RawPayloadIncluded || webhook.SecretValuePresent || webhook.PayloadSHA256 != "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" || !webhook.SignatureHeaderPresent || webhook.WebhookSecretRef != "env:STRIPE_WEBHOOK_REF" || webhook.Verified || len(webhook.Failures) == 0 {
		t.Fatalf("unexpected webhook ingest: %#v", webhook)
	}
	if webhook.Metadata["authorization"] != Redacted || webhook.Metadata["customer_ref"] != "cus_public" {
		t.Fatalf("webhook metadata was not sanitized as expected: %#v", webhook.Metadata)
	}

	req, err := http.NewRequest(http.MethodGet, server.URL+"/v1/projects/project_billing/billing/ledger?tenant_id=tenant_billing&api_key_id=key_billing", nil)
	if err != nil {
		t.Fatal(err)
	}
	ledger := doJSONForTest[BillingLedger](t, req, http.StatusOK)
	if ledger.Count != 0 || len(ledger.Events) != 0 {
		t.Fatalf("unexpected billing ledger: %#v", ledger)
	}
	encoded, err := json.Marshal(ledger)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), "synthetic-auth-fixture") || strings.Contains(string(encoded), "synthetic-secret-fixture") {
		t.Fatalf("billing ledger leaked raw secret material: %s", encoded)
	}
}

func TestHTTPHandlerProtectedRoutesRejectAuthMismatches(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Auth", "tenant_id": "tenant_auth", "project_id": "project_auth", "dataset_id": "dataset_auth", "dataset_name": "Dataset",
	})

	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/sdk-submit", JSONMap{
		"tenant_id": "tenant_other", "dataset_id": "dataset_auth", "agent_ref": "agent:auth", "run_id": "run_auth", "api_key_id": "key_auth", "idempotency_key": "idem_auth",
	}, "tenant_auth", "key_auth"), http.StatusForbidden, "tenant_mismatch")

	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/sdk-submit", JSONMap{
		"tenant_id": "tenant_auth", "dataset_id": "dataset_auth", "agent_ref": "agent:auth", "run_id": "run_auth", "api_key_id": "key_other", "idempotency_key": "idem_auth",
	}, "tenant_auth", "key_auth"), http.StatusForbidden, "api_key_mismatch")

	resp, err := http.DefaultClient.Do(authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/sdk-submit", JSONMap{
		"tenant_id": "tenant_auth", "dataset_id": "dataset_auth", "agent_ref": "agent:auth", "run_id": "run_auth", "api_key_id": "key_auth", "idempotency_key": "idem_auth_ok",
	}, "tenant_auth", "key_auth"))
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d", resp.StatusCode)
	}

	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/runs/run_auth/upload", JSONMap{
		"tenant_id": "tenant_other", "result": JSONMap{"status": "ok"}, "api_key_id": "key_auth", "idempotency_key": "idem_upload_auth",
	}, "tenant_auth", "key_auth"), http.StatusForbidden, "tenant_mismatch")

	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/runs/run_auth/upload", JSONMap{
		"tenant_id": "tenant_auth", "result": JSONMap{"status": "ok"}, "api_key_id": "key_other", "idempotency_key": "idem_upload_auth",
	}, "tenant_auth", "key_auth"), http.StatusForbidden, "api_key_mismatch")

	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/runs/run_auth/trace-events", JSONMap{
		"tenant_id": "tenant_other", "observations": []JSONMap{{"span_id": "span_auth"}}, "api_key_id": "key_auth", "idempotency_key": "idem_trace_auth",
	}, "tenant_auth", "key_auth"), http.StatusForbidden, "tenant_mismatch")

	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/runs/run_auth/trace-events", JSONMap{
		"tenant_id": "tenant_auth", "observations": []JSONMap{{"span_id": "span_auth"}}, "api_key_id": "key_other", "idempotency_key": "idem_trace_auth",
	}, "tenant_auth", "key_auth"), http.StatusForbidden, "api_key_mismatch")

	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodGet, server.URL+"/v1/projects/project_auth/usage?tenant_id=tenant_other&auth_key_id=key_auth", nil, "tenant_auth", "key_auth"), http.StatusForbidden, "tenant_mismatch")
	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodGet, server.URL+"/v1/projects/project_auth/usage?tenant_id=tenant_auth&auth_key_id=key_other", nil, "tenant_auth", "key_auth"), http.StatusForbidden, "api_key_mismatch")
	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodGet, server.URL+"/v1/projects/project_auth/audit-chain/verify?tenant_id=tenant_other&auth_key_id=key_auth", nil, "tenant_auth", "key_auth"), http.StatusForbidden, "tenant_mismatch")
	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodGet, server.URL+"/v1/projects/project_auth/audit-chain/verify?tenant_id=tenant_auth&auth_key_id=key_other", nil, "tenant_auth", "key_auth"), http.StatusForbidden, "api_key_mismatch")
}

func TestHTTPHandlerProtectedRoutesRejectMissingOrRawAPIKey(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Auth", "tenant_id": "tenant_auth", "project_id": "project_auth", "dataset_id": "dataset_auth", "dataset_name": "Dataset",
	})

	assertControlPlaneError(t, requestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/sdk-submit", JSONMap{
		"tenant_id": "tenant_auth", "dataset_id": "dataset_auth", "agent_ref": "agent:auth", "run_id": "run_missing", "idempotency_key": "idem_missing",
	}), http.StatusUnauthorized, "authentication_required")

	assertControlPlaneError(t, requestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/sdk-submit", JSONMap{
		"tenant_id": "tenant_auth", "dataset_id": "dataset_auth", "agent_ref": "agent:auth", "run_id": "run_secret", "api_key": "sk-test-never-read", "idempotency_key": "idem_secret",
	}), http.StatusBadRequest, "secret_input_rejected")

	req := requestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/sdk-submit", JSONMap{
		"tenant_id": "tenant_auth", "dataset_id": "dataset_auth", "agent_ref": "agent:auth", "run_id": "run_bad_auth", "idempotency_key": "idem_bad_auth",
	})
	req.Header.Set("Authorization", "Basic not-a-bearer")
	assertControlPlaneError(t, req, http.StatusBadRequest, "invalid_authorization_header")
}

func TestHTTPHandlerAPIKeyLifecycleScopesAndQuota(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Auth", "tenant_id": "tenant_keys", "project_id": "project_keys", "dataset_id": "dataset_keys", "dataset_name": "Dataset",
	})

	created := postJSONForTest[APIKeyCreateResult](t, server.URL+"/v1/projects/project_keys/api-keys", JSONMap{
		"tenant_id": "tenant_keys", "key_id": "key_submit", "name": "Submitter", "scopes": []string{ScopeRunSubmit, ScopeAPIKeyWrite}, "reveal_secret": true,
	})
	if created.OneTimeSecret == "" || !created.OneTimeSecretDisplayed || created.APIKey.SecretSHA256 != "" {
		t.Fatalf("unexpected created key response: %#v", created)
	}
	verified := postJSONForTest[APIKeyVerifyResult](t, server.URL+"/v1/projects/project_keys/api-keys/key_submit/verify", JSONMap{
		"tenant_id": "tenant_keys", "secret": created.OneTimeSecret, "scope": ScopeRunSubmit,
	})
	if !verified.Authenticated || verified.SecretValuePresent {
		t.Fatalf("unexpected verify response: %#v", verified)
	}
	postJSONWithHeadersForTest[APIKeyRateLimit](t, server.URL+"/v1/projects/project_keys/api-keys/key_submit/rate-limit", JSONMap{
		"tenant_id": "tenant_keys", "operation": "sdk_submit", "limit": 1,
	}, map[string]string{"Authorization": "Bearer " + created.OneTimeSecret})

	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_keys/runs/run_missing/upload", JSONMap{
		"tenant_id": "tenant_keys", "result": JSONMap{"status": "ok"}, "api_key_id": "key_submit",
	}, "tenant_keys", "key_submit"), http.StatusForbidden, "scope_denied")

	postJSONForTest[Run](t, server.URL+"/v1/projects/project_keys/sdk-submit", JSONMap{
		"tenant_id": "tenant_keys", "dataset_id": "dataset_keys", "agent_ref": "agent:key", "run_id": "run_quota", "api_key_id": "key_submit", "idempotency_key": "idem_key_submit",
	})
	postJSONForTest[Run](t, server.URL+"/v1/projects/project_keys/sdk-submit", JSONMap{
		"tenant_id": "tenant_keys", "dataset_id": "dataset_keys", "agent_ref": "agent:key", "run_id": "run_quota", "api_key_id": "key_submit", "idempotency_key": "idem_key_submit",
	})
	assertControlPlaneError(t, authenticatedRequestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_keys/sdk-submit", JSONMap{
		"tenant_id": "tenant_keys", "dataset_id": "dataset_keys", "agent_ref": "agent:key", "run_id": "run_quota_2", "api_key_id": "key_submit", "idempotency_key": "idem_key_submit_2",
	}, "tenant_keys", "key_submit"), http.StatusTooManyRequests, "quota_exceeded")
}

func TestHTTPHandlerBearerAPIKeySubmitAndDenials(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()
	postJSONForTest[BootstrapResult](t, server.URL+"/bootstrap", JSONMap{
		"tenant_name": "Tenant", "project_name": "Bearer", "tenant_id": "tenant_bearer", "project_id": "project_bearer", "dataset_id": "dataset_bearer", "dataset_name": "Dataset",
	})
	created := postJSONForTest[APIKeyCreateResult](t, server.URL+"/v1/projects/project_bearer/api-keys", JSONMap{
		"tenant_id": "tenant_bearer", "key_id": "key_bearer", "name": "Bearer submitter", "scopes": []string{ScopeRunSubmit, ScopeUsageRead, ScopeAPIKeyWrite}, "reveal_secret": true,
	})

	bearerReq := requestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_bearer/sdk-submit", JSONMap{
		"tenant_id": "tenant_bearer", "dataset_id": "dataset_bearer", "agent_ref": "agent:bearer", "run_id": "run_bearer", "idempotency_key": "idem_bearer",
	})
	bearerReq.Header.Set("Authorization", "Bearer "+created.OneTimeSecret)
	submit := doJSONForTest[Run](t, bearerReq, http.StatusOK)
	if submit.RunID != "run_bearer" || submit.Status != "queued" {
		t.Fatalf("unexpected bearer submit: %#v", submit)
	}
	usageReq := requestForTest(t, http.MethodGet, server.URL+"/v1/projects/project_bearer/usage?tenant_id=tenant_bearer", nil)
	usageReq.Header.Set("Authorization", "Bearer "+created.OneTimeSecret)
	usage := doJSONForTest[UsageSnapshot](t, usageReq, http.StatusOK)
	if operationTotalCount(usage.OperationTotals, "sdk.submit") != 1 {
		t.Fatalf("bearer submit did not record sdk_submit usage: %#v", usage.OperationTotals)
	}

	mismatch := requestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_bearer/sdk-submit", JSONMap{
		"tenant_id": "tenant_bearer", "dataset_id": "dataset_bearer", "agent_ref": "agent:bearer", "run_id": "run_mismatch", "api_key_id": "other_key", "idempotency_key": "idem_mismatch",
	})
	mismatch.Header.Set("Authorization", "Bearer "+created.OneTimeSecret)
	assertControlPlaneError(t, mismatch, http.StatusForbidden, "api_key_mismatch")

	wrongScope := requestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_bearer/runs/run_bearer/upload", JSONMap{
		"tenant_id": "tenant_bearer", "result": JSONMap{"status": "ok"},
	})
	wrongScope.Header.Set("Authorization", "Bearer "+created.OneTimeSecret)
	assertControlPlaneError(t, wrongScope, http.StatusForbidden, "scope_denied")
}

func TestHTTPHandlerJSONErrorEnvelope(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()

	resp, err := http.Post(server.URL+"/bootstrap", "application/json", bytes.NewBufferString(`{"tenant_name"`))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusBadRequest {
		t.Fatalf("status = %d", resp.StatusCode)
	}
	var body struct {
		Status string `json:"status"`
		Error  struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.Status != "error" || body.Error.Code != "invalid_json" || body.Error.Message == "" {
		t.Fatalf("unexpected error envelope: %#v", body)
	}
}

func postJSONForTest[T any](t *testing.T, url string, payload any) T {
	t.Helper()
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	resp, err := http.Post(url, "application/json", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		t.Fatalf("status = %d", resp.StatusCode)
	}
	var output T
	if err := json.NewDecoder(resp.Body).Decode(&output); err != nil {
		t.Fatal(err)
	}
	return output
}

func doJSONForTest[T any](t *testing.T, req *http.Request, wantStatus int) T {
	t.Helper()
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != wantStatus {
		var failure JSONMap
		_ = json.NewDecoder(resp.Body).Decode(&failure)
		t.Fatalf("status = %d, want %d body=%#v", resp.StatusCode, wantStatus, failure)
	}
	var output T
	if err := json.NewDecoder(resp.Body).Decode(&output); err != nil {
		t.Fatal(err)
	}
	return output
}

func postJSONWithHeadersForTest[T any](t *testing.T, url string, payload any, headers map[string]string) T {
	t.Helper()
	body, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	return doJSONForTest[T](t, req, http.StatusOK)
}

func requestForTest(t *testing.T, method, url string, payload any) *http.Request {
	t.Helper()
	var body *bytes.Reader
	if payload == nil {
		body = bytes.NewReader(nil)
	} else {
		encoded, err := json.Marshal(payload)
		if err != nil {
			t.Fatal(err)
		}
		body = bytes.NewReader(encoded)
	}
	req, err := http.NewRequest(method, url, body)
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Content-Type", "application/json")
	return req
}

func authenticatedRequestForTest(t *testing.T, method, url string, payload any, tenantID, apiKeyID string) *http.Request {
	t.Helper()
	req := requestForTest(t, method, url, payload)
	req.Header.Set("X-Ashr-Tenant-ID", tenantID)
	req.Header.Set("X-Ashr-API-Key-ID", apiKeyID)
	return req
}

func routeScopeDocGroupByName(docs RouteScopeDocs, name string) *RouteScopeDocGroup {
	for i := range docs.RouteGroups {
		if docs.RouteGroups[i].Name == name {
			return &docs.RouteGroups[i]
		}
	}
	return nil
}
func routeScopeDocsWithoutGroup(docs RouteScopeDocs, name string) RouteScopeDocs {
	filtered := docs
	filtered.RouteGroups = []RouteScopeDocGroup{}
	for _, group := range docs.RouteGroups {
		if group.Name != name {
			filtered.RouteGroups = append(filtered.RouteGroups, group)
		}
	}
	return filtered
}
func routeScopeDocPlanByName(docs RouteScopeDocs, name string) *RouteScopeDocPlan {
	for i := range docs.PlanLimits {
		if docs.PlanLimits[i].Plan == name {
			return &docs.PlanLimits[i]
		}
	}
	return nil
}

func assertRouteScopePlanLimit(t *testing.T, plan *RouteScopeDocPlan, metric string, limit int, unit string) {
	t.Helper()
	for _, item := range plan.Limits {
		if item.Metric == metric {
			if item.Limit != limit || item.Unit != unit {
				t.Fatalf("%s %s limit = %d %s, want %d %s", plan.Plan, metric, item.Limit, item.Unit, limit, unit)
			}
			return
		}
	}
	t.Fatalf("%s plan missing %s limit: %#v", plan.Plan, metric, plan.Limits)
}

func operationTotalCount(totals []UsageOperationTotal, operation string) int {
	for _, total := range totals {
		if total.Operation == operation {
			return total.Events
		}
	}
	return 0
}
func stringSliceContains(items []string, want string) bool {
	for _, item := range items {
		if item == want {
			return true
		}
	}
	return false
}

func assertControlPlaneError(t *testing.T, req *http.Request, wantStatus int, wantCode string) struct {
	Status string `json:"status"`
	Error  struct {
		Code      string `json:"code"`
		Operation string `json:"operation"`
		Meter     string `json:"meter"`
		Limit     int    `json:"limit"`
		Used      int    `json:"used"`
		Requested int    `json:"requested"`
		Remaining int    `json:"remaining"`
	} `json:"error"`
} {
	t.Helper()
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != wantStatus {
		t.Fatalf("status = %d, want %d", resp.StatusCode, wantStatus)
	}
	var body struct {
		Status string `json:"status"`
		Error  struct {
			Code      string `json:"code"`
			Operation string `json:"operation"`
			Meter     string `json:"meter"`
			Limit     int    `json:"limit"`
			Used      int    `json:"used"`
			Requested int    `json:"requested"`
			Remaining int    `json:"remaining"`
		} `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.Status != "error" || body.Error.Code != wantCode {
		t.Fatalf("unexpected error envelope: %#v, want code %q", body, wantCode)
	}
	return body
}
