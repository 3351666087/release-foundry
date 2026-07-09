package ashrclone

import "testing"

func TestOperationMeterForNormalizesPublicOperations(t *testing.T) {
	tests := []struct {
		operation string
		wantOp    string
		wantMeter string
		wantUnit  string
		wantQty   int
	}{
		{operation: "sdk_submit", wantOp: "sdk.submit", wantMeter: QuotaMeterRuns, wantUnit: "count", wantQty: 1},
		{operation: "upload_run", wantOp: "run.upload", wantMeter: QuotaMeterMedia, wantUnit: "count", wantQty: 1},
		{operation: "ingest_trace", wantOp: "trace.ingest", wantMeter: QuotaMeterObservations, wantUnit: "count", wantQty: 1},
		{operation: "artifact_manifest", wantOp: "artifact.manifest", wantMeter: QuotaMeterStorageBytes, wantUnit: "bytes", wantQty: 0},
		{operation: "worker.job.enqueue", wantOp: "worker.job.enqueue", wantMeter: QuotaMeterRuns, wantUnit: "count", wantQty: 1},
		{operation: "worker.job.lease", wantOp: "worker.job.lease", wantMeter: QuotaMeterRuns, wantUnit: "count", wantQty: 0},
	}
	for _, test := range tests {
		meter, ok := OperationMeterFor(test.operation)
		if !ok {
			t.Fatalf("%s did not return a meter", test.operation)
		}
		if meter.Operation != test.wantOp || meter.Meter != test.wantMeter || meter.Unit != test.wantUnit || meter.DefaultQuantity != test.wantQty {
			t.Fatalf("%s meter = %#v", test.operation, meter)
		}
	}
	if _, ok := OperationMeterFor("custom.meter"); ok {
		t.Fatal("unknown quota operation unexpectedly returned a meter")
	}
}

func TestQuotaExceededErrorPublicSchemaIsSafeAndStable(t *testing.T) {
	detail := QuotaExceededError{Operation: "upload_run", Limit: 5, Used: 4, Requested: 2}.PublicSchema()
	if detail.Code != "quota_exceeded" || detail.Operation != "run.upload" || detail.Meter != QuotaMeterMedia || detail.Unit != "count" {
		t.Fatalf("unexpected quota schema identity: %#v", detail)
	}
	if detail.Limit != 5 || detail.Used != 4 || detail.Requested != 2 || detail.Remaining != 1 {
		t.Fatalf("unexpected quota schema amounts: %#v", detail)
	}
	if detail.Message == "" {
		t.Fatalf("expected public message: %#v", detail)
	}
}

func TestQuotaRepositoryConformance(t *testing.T) {
	var _ QuotaRepository = (*MemoryService)(nil)
	var _ QuotaRepository = (*PostgresRepository)(nil)
}
