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
	submit, err := client.SubmitRunHTTP(context.Background(), "tenant_http", "project_http", SubmitRunOptions{DatasetID: "dataset_http", AgentRef: "agent:http", RunID: "run_http", IdempotencyKey: "idem_submit"})
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
	enqueued, err := client.EnqueueWorkerJobHTTP(context.Background(), "tenant_workers", "project_workers", JSONMap{"gate": "candidate"}, EnqueueWorkerJobHTTPOptions{JobType: "release_gate", TargetID: "run_workers", JobID: "job_workers", MaxAttempts: 2, IdempotencyKey: "idem_workers"})
	if err != nil {
		t.Fatal(err)
	}
	if enqueued.Operation != "worker.job.enqueue" || enqueued.Result["job_id"] != "job_workers" {
		t.Fatalf("unexpected enqueue response: %#v", enqueued)
	}

	leased, err := client.LeaseWorkerJobHTTP(context.Background(), "tenant_workers", "project_workers", LeaseWorkerJobHTTPOptions{LeaseOwnerID: "worker_1", JobType: "release_gate"})
	if err != nil {
		t.Fatal(err)
	}
	if leased.Operation != "worker.job.lease" || leased.Result["leased"] != true {
		t.Fatalf("unexpected lease response: %#v", leased)
	}

	completed, err := client.CompleteWorkerJobHTTP(context.Background(), "tenant_workers", "project_workers", "job_workers", JSONMap{"status": "ok"}, WorkerJobLeaseActionHTTPOptions{LeaseOwnerID: "worker_1"})
	if err != nil {
		t.Fatal(err)
	}
	if completed.Operation != "worker.job.complete" || completed.Result["status"] != WorkerJobStatusCompleted {
		t.Fatalf("unexpected complete response: %#v", completed)
	}

	listed, err := client.ListWorkerJobsHTTP(context.Background(), "tenant_workers", "project_workers", ListWorkerJobsHTTPOptions{Status: WorkerJobStatusCompleted})
	if err != nil {
		t.Fatal(err)
	}
	if listed.Operation != "worker.job.list" || listed.Result["count"].(float64) != 1 {
		t.Fatalf("unexpected list response: %#v", listed)
	}
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
