package ashrclone

import (
	"errors"
	"testing"
)

func TestMemoryServiceIdempotentSubmitReplaysAndConflicts(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject("Enterprise Tenant", "Release Gate", Dataset{Name: "Calibration"}, "tenant_saas", "project_saas")
	if err != nil {
		t.Fatal(err)
	}
	first, err := service.SubmitRun(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, boot.Result.Dataset.DatasetID, "agent:v1", "run_idem", JSONMap{"purpose": "test"}, IdempotencyOptions{Key: "idem_submit", APIKeyID: "key_idem"})
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.SubmitRun(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, boot.Result.Dataset.DatasetID, "agent:v1", "run_idem", JSONMap{"purpose": "test"}, IdempotencyOptions{Key: "idem_submit", APIKeyID: "key_idem"})
	if err != nil {
		t.Fatal(err)
	}
	if !replay.IdempotentReplay || replay.Result.RunID != first.Result.RunID {
		t.Fatalf("expected replay of %q, got %#v", first.Result.RunID, replay)
	}
	_, err = service.SubmitRun(boot.Result.Tenant.TenantID, boot.Result.Project.ProjectID, boot.Result.Dataset.DatasetID, "agent:v2", "run_idem_conflict", nil, IdempotencyOptions{Key: "idem_submit"})
	var conflict IdempotencyConflictError
	if !errors.As(err, &conflict) {
		t.Fatalf("expected idempotency conflict, got %T %v", err, err)
	}
}
