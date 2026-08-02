package releasefoundry

import (
	"errors"
	"testing"
)

func TestEventSpoolTraceReplayIsIdempotentForQuotaLifecycleAndConflicts(t *testing.T) {
	service := NewMemoryService()
	boot, err := service.BootstrapProject(
		"A1 trace tenant",
		"A1 trace project",
		Dataset{Name: "A1 trace dataset"},
		"tenant_event_spool",
		"project_event_spool",
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.ConfigureUsageQuota("tenant_event_spool", "project_event_spool", "trace.ingest", 2); err != nil {
		t.Fatal(err)
	}
	if _, err := service.SubmitRun(
		"tenant_event_spool",
		"project_event_spool",
		boot.Result.Dataset.DatasetID,
		"agent:event-spool",
		"run_event_spool",
		nil,
		IdempotencyOptions{Key: "submit-event-spool"},
	); err != nil {
		t.Fatal(err)
	}

	observations := []JSONMap{
		{"event_id": "one", "content": "first"},
		{"event_id": "two", "content": "second"},
	}
	options := IngestTraceOptions{
		BatchID:        "batch_event_spool",
		IdempotencyKey: "spool-idempotency-0001",
		RequestID:      "request-event-spool-0001",
	}
	first, err := service.IngestTrace(
		"tenant_event_spool",
		"project_event_spool",
		"run_event_spool",
		observations,
		options,
	)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.IngestTrace(
		"tenant_event_spool",
		"project_event_spool",
		"run_event_spool",
		observations,
		options,
	)
	if err != nil {
		t.Fatal(err)
	}
	if !replay.IdempotentReplay {
		t.Fatalf("expected exact flush replay to be marked idempotent, got %#v", replay)
	}
	if replay.Result.BatchID != first.Result.BatchID || replay.Result.ObservationsSHA256 != first.Result.ObservationsSHA256 {
		t.Fatalf("replay changed trace batch identity or digest: first=%#v replay=%#v", first.Result, replay.Result)
	}

	usage, err := service.UsageSnapshot("tenant_event_spool", "project_event_spool")
	if err != nil {
		t.Fatal(err)
	}
	traceUsage := usageTotalForOperation(usage.Result.OperationTotals, "trace.ingest")
	if traceUsage.Units != 2 || traceUsage.Events != 1 {
		t.Fatalf("exact replay must not double-count trace quota: %#v", usage.Result.OperationTotals)
	}
	lifecycle, err := service.RunLifecycle("tenant_event_spool", "project_event_spool", "run_event_spool")
	if err != nil {
		t.Fatal(err)
	}
	if len(lifecycle.Result.TraceBatches) != 1 || lifecycle.Result.Counts["trace_batches"] != 1 {
		t.Fatalf("exact replay must not create a second trace batch: %#v", lifecycle.Result)
	}

	changed := []JSONMap{
		{"event_id": "one", "content": "changed"},
		{"event_id": "two", "content": "second"},
	}
	_, err = service.IngestTrace(
		"tenant_event_spool",
		"project_event_spool",
		"run_event_spool",
		changed,
		options,
	)
	var conflict IdempotencyConflictError
	if !errors.As(err, &conflict) {
		t.Fatalf("changed payload with the same spool idempotency key must conflict, got %T %v", err, err)
	}
	usageAfterConflict, err := service.UsageSnapshot("tenant_event_spool", "project_event_spool")
	if err != nil {
		t.Fatal(err)
	}
	traceUsageAfterConflict := usageTotalForOperation(usageAfterConflict.Result.OperationTotals, "trace.ingest")
	if traceUsageAfterConflict.Units != 2 || traceUsageAfterConflict.Events != 1 {
		t.Fatalf("idempotency conflict must not consume quota: %#v", usageAfterConflict.Result.OperationTotals)
	}
}

func usageTotalForOperation(totals []UsageOperationTotal, operation string) UsageOperationTotal {
	for _, total := range totals {
		if total.Operation == operation {
			return total
		}
	}
	return UsageOperationTotal{Operation: operation}
}
