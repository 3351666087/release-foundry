package releasefoundry

import (
	"strings"
	"time"
)

const (
	QuotaMeterRuns         = "runs"
	QuotaMeterMedia        = "media"
	QuotaMeterObservations = "observations"
	QuotaMeterStorageBytes = "storage_bytes"
)

const (
	usageOperationSubmit            = "sdk.submit"
	usageOperationRunUpload         = "run.upload"
	usageOperationTraceIngest       = "trace.ingest"
	usageOperationArtifactManifest  = "artifact.manifest"
	usageOperationWorkerJobEnqueue  = "worker.job.enqueue"
	usageOperationWorkerJobLease    = "worker.job.lease"
	usageOperationWorkerJobComplete = "worker.job.complete"
	usageOperationWorkerJobFail     = "worker.job.fail"
)

type OperationMeter struct {
	Operation       string `json:"operation"`
	Meter           string `json:"meter"`
	Unit            string `json:"unit"`
	DefaultQuantity int    `json:"default_quantity"`
}

type QuotaUsageAppend struct {
	Operation      string    `json:"operation"`
	Units          int       `json:"units"`
	APIKeyID       string    `json:"api_key_id,omitempty"`
	IdempotencyKey string    `json:"idempotency_key,omitempty"`
	RequestID      string    `json:"request_id,omitempty"`
	RunID          string    `json:"run_id,omitempty"`
	TargetID       string    `json:"target_id,omitempty"`
	CreatedAt      time.Time `json:"created_at,omitempty"`
}

type QuotaPolicyRepository interface {
	ConfigureUsageQuota(tenantID, projectID, operation string, limit int) (Envelope[UsageOperationTotal], error)
}

type QuotaUsageAppendRepository interface {
	AppendQuotaUsage(tenantID, projectID string, event QuotaUsageAppend) (Envelope[UsageOperationTotal], error)
}

type QuotaRollupRepository interface {
	UsageSnapshot(tenantID, projectID string) (Envelope[UsageSnapshot], error)
}

type QuotaRepository interface {
	QuotaPolicyRepository
	QuotaUsageAppendRepository
	QuotaRollupRepository
}

var operationMeters = map[string]OperationMeter{
	usageOperationSubmit:            {Operation: usageOperationSubmit, Meter: QuotaMeterRuns, Unit: "count", DefaultQuantity: 1},
	usageOperationRunUpload:         {Operation: usageOperationRunUpload, Meter: QuotaMeterMedia, Unit: "count", DefaultQuantity: 1},
	usageOperationTraceIngest:       {Operation: usageOperationTraceIngest, Meter: QuotaMeterObservations, Unit: "count", DefaultQuantity: 1},
	usageOperationArtifactManifest:  {Operation: usageOperationArtifactManifest, Meter: QuotaMeterStorageBytes, Unit: "bytes", DefaultQuantity: 0},
	usageOperationWorkerJobEnqueue:  {Operation: usageOperationWorkerJobEnqueue, Meter: QuotaMeterRuns, Unit: "count", DefaultQuantity: 1},
	usageOperationWorkerJobLease:    {Operation: usageOperationWorkerJobLease, Meter: QuotaMeterRuns, Unit: "count", DefaultQuantity: 0},
	usageOperationWorkerJobComplete: {Operation: usageOperationWorkerJobComplete, Meter: QuotaMeterRuns, Unit: "count", DefaultQuantity: 0},
	usageOperationWorkerJobFail:     {Operation: usageOperationWorkerJobFail, Meter: QuotaMeterRuns, Unit: "count", DefaultQuantity: 0},
}

func OperationMeterFor(operation string) (OperationMeter, bool) {
	operation = NormalizeQuotaOperation(operation)
	if operation == "" {
		return OperationMeter{}, false
	}
	if meter, ok := operationMeters[operation]; ok {
		return meter, true
	}
	return OperationMeter{}, false
}

func NormalizeQuotaOperation(operation string) string {
	switch strings.TrimSpace(operation) {
	case "sdk_submit":
		return usageOperationSubmit
	case "upload_run":
		return usageOperationRunUpload
	case "ingest_trace":
		return usageOperationTraceIngest
	case "artifact_manifest":
		return usageOperationArtifactManifest
	default:
		return strings.TrimSpace(operation)
	}
}

func quotaUnits(units int) int {
	if units <= 0 {
		return 1
	}
	return units
}
