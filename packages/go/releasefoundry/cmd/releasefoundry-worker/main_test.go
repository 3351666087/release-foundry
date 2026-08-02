package main

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
)

func TestWorkerCommandConfigFromEnvUsesAliasesAndParsesDurations(t *testing.T) {
	env := map[string]string{
		"RELEASEFOUNDRY_TENANT_ID":                 "tenant_a",
		"RELEASEFOUNDRY_PROJECT_ID":                "project_a",
		"RELEASEFOUNDRY_WORKER_LEASE_OWNER_ID":     "worker_a",
		"RELEASEFOUNDRY_WORKER_JOB_TYPE":           "release_gate",
		"RELEASEFOUNDRY_WORKER_MAX_JOBS":           "7",
		"RELEASEFOUNDRY_WORKER_MAX_IDLE_LEASES":    "3",
		"RELEASEFOUNDRY_WORKER_LEASE_SECONDS":      "120",
		"RELEASEFOUNDRY_WORKER_HEARTBEAT_INTERVAL": "2s",
		"RELEASEFOUNDRY_WORKER_REQUEST_ID":         "req_123",
		"RELEASEFOUNDRY_WORKER_API_KEY_ID":         "key_public_id",
	}

	config, err := workerCommandConfigFromEnv(mapLookup(env))
	if err != nil {
		t.Fatal(err)
	}
	options := config.Options
	if options.TenantID != "tenant_a" || options.ProjectID != "project_a" || options.LeaseOwnerID != "worker_a" || options.JobType != "release_gate" {
		t.Fatalf("unexpected identity options: %#v", options)
	}
	if options.MaxJobs != 7 || options.MaxIdleLeases != 3 || options.LeaseSeconds != 120 || options.HeartbeatInterval != 2*time.Second {
		t.Fatalf("unexpected limit options: %#v", options)
	}
	if options.RequestID != "req_123" || options.APIKeyID != "key_public_id" {
		t.Fatalf("unexpected request metadata: %#v", options)
	}
}

func TestWorkerCommandConfigFromEnvParsesHeartbeatSeconds(t *testing.T) {
	config, err := workerCommandConfigFromEnv(mapLookup(map[string]string{"RELEASEFOUNDRY_WORKER_HEARTBEAT_INTERVAL": "15"}))
	if err != nil {
		t.Fatal(err)
	}
	if config.Options.HeartbeatInterval != 15*time.Second {
		t.Fatalf("expected integer heartbeat to be seconds, got %s", config.Options.HeartbeatInterval)
	}
}

func TestWorkerCommandConfigFromEnvDoesNotRequirePostgresDSN(t *testing.T) {
	config, err := workerCommandConfigFromEnv(mapLookup(map[string]string{
		"RELEASEFOUNDRY_WORKER_TENANT_ID":      "tenant_a",
		"RELEASEFOUNDRY_WORKER_PROJECT_ID":     "project_a",
		"RELEASEFOUNDRY_WORKER_LEASE_OWNER_ID": "worker_a",
	}))
	if err != nil {
		t.Fatal(err)
	}
	if config.Options.TenantID != "tenant_a" || config.Options.ProjectID != "project_a" || config.Options.LeaseOwnerID != "worker_a" {
		t.Fatalf("unexpected worker options without postgres DSN: %#v", config.Options)
	}
}

func TestWorkerCommandConfigFromEnvRejectsInvalidNumbers(t *testing.T) {
	_, err := workerCommandConfigFromEnv(mapLookup(map[string]string{"RELEASEFOUNDRY_WORKER_MAX_JOBS": "many"}))
	if err == nil || !strings.Contains(err.Error(), "RELEASEFOUNDRY_WORKER_MAX_JOBS") {
		t.Fatalf("expected named parse error, got %v", err)
	}
}

func TestHandleWorkerJobReturnsPublicSafeMetadata(t *testing.T) {
	result, err := handleWorkerJob(context.Background(), releasefoundry.WorkerJob{JobID: "job_1", JobType: "release_gate", PayloadSHA256: "sha_123"})
	if err != nil {
		t.Fatal(err)
	}
	if result["handler"] != commandName || result["job_id"] != "job_1" || result["payload_sha256"] != "sha_123" || result["public_safe"] != true {
		t.Fatalf("unexpected handler result: %#v", result)
	}
	if _, ok := result["payload"]; ok {
		t.Fatalf("handler result must not include raw payload: %#v", result)
	}
}

func mapLookup(values map[string]string) func(string) (string, bool) {
	return func(key string) (string, bool) {
		value, ok := values[key]
		return value, ok
	}
}
