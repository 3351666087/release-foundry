package ashrclone

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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

func TestHTTPHandlerRouteManifestIncludesRunFamilies(t *testing.T) {
	server := httptest.NewServer(NewHTTPHandler(NewMemoryService()))
	defer server.Close()

	resp, err := http.Get(server.URL + "/openapi.json")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var body struct {
		Routes []string `json:"routes"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	want := map[string]bool{
		"GET /v1/projects/{project_id}/usage":                             false,
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

	req := requestForTest(t, http.MethodPost, server.URL+"/v1/projects/project_auth/sdk-submit", JSONMap{
		"tenant_id": "tenant_auth", "dataset_id": "dataset_auth", "agent_ref": "agent:auth", "run_id": "run_secret", "api_key_id": "key_auth", "idempotency_key": "idem_secret",
	})
	req.Header.Set("Authorization", "Bearer sk-test-never-read")
	assertControlPlaneError(t, req, http.StatusBadRequest, "secret_input_rejected")
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

func assertControlPlaneError(t *testing.T, req *http.Request, wantStatus int, wantCode string) {
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
			Code string `json:"code"`
		} `json:"error"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.Status != "error" || body.Error.Code != wantCode {
		t.Fatalf("unexpected error envelope: %#v, want code %q", body, wantCode)
	}
}
