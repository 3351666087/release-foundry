package ashrclone

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"
)

type MemoryService struct {
	mu                sync.Mutex
	tenants           map[string]Tenant
	projects          map[string]Project
	datasets          map[string]Dataset
	runs              map[string]Run
	runUploads        map[string]RunUpload
	traceBatches      map[string]TraceBatch
	artifactManifests map[string]ArtifactManifest
	workerJobs        map[string]WorkerJob
	apiKeys           map[string]APIKeyRecord
	apiKeyRateLimits  map[string]APIKeyRateLimit
	usageEvents       []usageEvent
	usageQuotaLimits  map[string]int
	auditEvents       []AuditEvent
	idem              map[string]idemRecord
	nextID            int
}

type usageEvent struct {
	TenantID  string
	ProjectID string
	Operation string
	Units     int
	Events    int
}

func NewMemoryService() *MemoryService {
	return &MemoryService{
		tenants:           map[string]Tenant{},
		projects:          map[string]Project{},
		datasets:          map[string]Dataset{},
		runs:              map[string]Run{},
		runUploads:        map[string]RunUpload{},
		traceBatches:      map[string]TraceBatch{},
		artifactManifests: map[string]ArtifactManifest{},
		workerJobs:        map[string]WorkerJob{},
		apiKeys:           map[string]APIKeyRecord{},
		apiKeyRateLimits:  map[string]APIKeyRateLimit{},
		usageEvents:       []usageEvent{},
		usageQuotaLimits:  map[string]int{},
		auditEvents:       []AuditEvent{},
		idem:              map[string]idemRecord{},
		nextID:            1,
	}
}

func (service *MemoryService) BootstrapProject(tenantName, projectName string, dataset Dataset, tenantID, projectID string) (Envelope[BootstrapResult], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	if tenantID == "" {
		tenantID = service.id("tenant", tenantName)
	}
	if projectID == "" {
		projectID = service.id("project", projectName)
	}
	if dataset.DatasetID == "" {
		dataset.DatasetID = service.id("dataset", dataset.Name)
	}
	if dataset.Name == "" {
		dataset.Name = "SDK Bootstrap Dataset"
	}
	tenant := Tenant{TenantID: tenantID, Name: tenantName}
	project := Project{TenantID: tenantID, ProjectID: projectID, Name: projectName}
	dataset.TenantID = tenantID
	dataset.ProjectID = projectID
	service.tenants[tenantID] = tenant
	service.projects[projectKey(tenantID, projectID)] = project
	service.datasets[datasetKey(tenantID, projectID, dataset.DatasetID)] = dataset
	return Envelope[BootstrapResult]{Operation: "bootstrap_project", Status: "ok", Result: BootstrapResult{Tenant: tenant, Project: project, Dataset: dataset}}, nil
}

func (service *MemoryService) CreateDataset(tenantID, projectID string, dataset Dataset, options IdempotencyOptions) (Envelope[Dataset], error) {
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "dataset": dataset}
	if options.Key != "" {
		if replay, ok, err := service.idempotentReplay("create_dataset", tenantID, projectID, options.Key, request); err != nil || ok {
			if err != nil {
				return Envelope[Dataset]{}, err
			}
			result := replay.(Envelope[Dataset])
			result.IdempotentReplay = true
			return result, nil
		}
	}

	service.mu.Lock()
	defer service.mu.Unlock()
	if dataset.DatasetID == "" {
		dataset.DatasetID = service.id("dataset", dataset.Name)
	}
	dataset.TenantID = tenantID
	dataset.ProjectID = projectID
	service.datasets[datasetKey(tenantID, projectID, dataset.DatasetID)] = dataset
	response := Envelope[Dataset]{Operation: "create_dataset", Status: "ok", Result: dataset}
	service.storeIdempotencyLocked("create_dataset", tenantID, projectID, options.Key, request, response)
	return response, nil
}

func (service *MemoryService) SubmitRun(tenantID, projectID, datasetID, agentRef, runID string, metadata JSONMap, options IdempotencyOptions) (Envelope[Run], error) {
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "dataset_id": datasetID, "agent_ref": agentRef, "run_id": runID, "metadata": metadata}
	if options.Key != "" {
		if replay, ok, err := service.idempotentReplay("sdk_submit", tenantID, projectID, options.Key, request); err != nil || ok {
			if err != nil {
				return Envelope[Run]{}, err
			}
			result := replay.(Envelope[Run])
			result.IdempotentReplay = true
			return result, nil
		}
	}

	service.mu.Lock()
	defer service.mu.Unlock()
	if err := service.authorizeAndConsumeLocked(tenantID, projectID, options.APIKeyID, ScopeRunSubmit, "sdk_submit", usageOperationSubmit, 1); err != nil {
		return Envelope[Run]{}, err
	}
	if runID == "" {
		runID = service.id("run", datasetID)
	}
	mergedMetadata := JSONMap{"client": SaaSClientVersion}
	for key, value := range metadata {
		mergedMetadata[key] = value
	}
	run := Run{TenantID: tenantID, ProjectID: projectID, DatasetID: datasetID, RunID: runID, AgentRef: agentRef, Status: "queued", Metadata: mergedMetadata}
	service.runs[runKey(tenantID, projectID, runID)] = run
	response := Envelope[Run]{Operation: "sdk_submit", Status: "ok", Result: run}
	service.storeIdempotencyLocked("sdk_submit", tenantID, projectID, options.Key, request, response)
	return response, nil
}

func (service *MemoryService) UploadRun(tenantID, projectID, runID string, result JSONMap, options UploadRunOptions) (Envelope[RunUpload], error) {
	if err := ValidateMediaSafeEnvelope(result); err != nil {
		return Envelope[RunUpload]{}, err
	}
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "run_id": runID, "result": result, "upload_id": options.UploadID}
	if options.IdempotencyKey != "" {
		if replay, ok, err := service.idempotentReplay("upload_run", tenantID, projectID, options.IdempotencyKey, request); err != nil || ok {
			if err != nil {
				return Envelope[RunUpload]{}, err
			}
			response := replay.(Envelope[RunUpload])
			response.IdempotentReplay = true
			return response, nil
		}
	}

	service.mu.Lock()
	defer service.mu.Unlock()
	if err := service.authorizeAndConsumeLocked(tenantID, projectID, options.APIKeyID, ScopeRunUpload, "upload_run", "", 0); err != nil {
		return Envelope[RunUpload]{}, err
	}
	run, ok := service.runs[runKey(tenantID, projectID, runID)]
	if !ok {
		return Envelope[RunUpload]{}, NotFoundError{Resource: "run"}
	}
	if err := service.checkUsageQuotaLocked(tenantID, projectID, usageOperationRunUpload, 1); err != nil {
		return Envelope[RunUpload]{}, err
	}
	uploadID := options.UploadID
	if uploadID == "" {
		uploadID = service.id("upload", runID)
	}
	now := time.Now().UTC()
	upload := RunUpload{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, UploadID: uploadID, ResultSHA256: mustFingerprint(result), RawPayloadIncluded: false, APIKeyID: options.APIKeyID, RequestID: options.RequestID, CreatedAt: now}
	service.runUploads[runUploadKey(tenantID, projectID, runID, uploadID)] = upload
	run.Status = "uploaded"
	service.runs[runKey(tenantID, projectID, runID)] = run
	service.recordUsageEventLocked(tenantID, projectID, usageOperationRunUpload, 1)
	service.appendAuditEventLocked(tenantID, projectID, "upload_run", runID, options.APIKeyID, options.IdempotencyKey, options.RequestID, JSONMap{"run_id": runID, "upload_id": uploadID, "result_sha256": upload.ResultSHA256}, now)
	response := Envelope[RunUpload]{Operation: "upload_run", Status: "ok", Result: upload}
	service.storeIdempotencyLocked("upload_run", tenantID, projectID, options.IdempotencyKey, request, response)
	return response, nil
}

func (service *MemoryService) IngestTrace(tenantID, projectID, runID string, observations []JSONMap, options IngestTraceOptions) (Envelope[TraceBatch], error) {
	if err := ValidateMediaSafeEnvelope(observations); err != nil {
		return Envelope[TraceBatch]{}, err
	}
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "run_id": runID, "observations": observations, "batch_id": options.BatchID}
	if options.IdempotencyKey != "" {
		if replay, ok, err := service.idempotentReplay("ingest_trace", tenantID, projectID, options.IdempotencyKey, request); err != nil || ok {
			if err != nil {
				return Envelope[TraceBatch]{}, err
			}
			response := replay.(Envelope[TraceBatch])
			response.IdempotentReplay = true
			return response, nil
		}
	}

	service.mu.Lock()
	defer service.mu.Unlock()
	units := len(observations)
	if units < 1 {
		units = 1
	}
	if err := service.authorizeAndConsumeLocked(tenantID, projectID, options.APIKeyID, ScopeTraceIngest, "ingest_trace", "", 0); err != nil {
		return Envelope[TraceBatch]{}, err
	}
	if _, ok := service.runs[runKey(tenantID, projectID, runID)]; !ok {
		return Envelope[TraceBatch]{}, NotFoundError{Resource: "run"}
	}
	if err := service.checkUsageQuotaLocked(tenantID, projectID, usageOperationTraceIngest, units); err != nil {
		return Envelope[TraceBatch]{}, err
	}
	batchID := options.BatchID
	if batchID == "" {
		batchID = service.id("trace_batch", runID)
	}
	now := time.Now().UTC()
	batch := TraceBatch{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, BatchID: batchID, ObservationCount: len(observations), ObservationsSHA256: mustFingerprint(observations), RawPayloadIncluded: false, APIKeyID: options.APIKeyID, RequestID: options.RequestID, CreatedAt: now}
	service.traceBatches[traceBatchKey(tenantID, projectID, runID, batchID)] = batch
	service.recordUsageEventLocked(tenantID, projectID, usageOperationTraceIngest, units)
	service.appendAuditEventLocked(tenantID, projectID, "ingest_trace", runID, options.APIKeyID, options.IdempotencyKey, options.RequestID, JSONMap{"run_id": runID, "batch_id": batchID, "observations_sha256": batch.ObservationsSHA256, "observation_count": len(observations)}, now)
	response := Envelope[TraceBatch]{Operation: "ingest_trace", Status: "ok", Result: batch}
	service.storeIdempotencyLocked("ingest_trace", tenantID, projectID, options.IdempotencyKey, request, response)
	return response, nil
}

func (service *MemoryService) CreateArtifactManifest(tenantID, projectID, runID string, manifest JSONMap, options ArtifactManifestOptions) (Envelope[ArtifactManifest], error) {
	if err := ValidateMediaSafeEnvelope(manifest); err != nil {
		return Envelope[ArtifactManifest]{}, err
	}
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "run_id": runID, "manifest": manifest, "artifact_id": options.ArtifactID}
	if options.IdempotencyKey != "" {
		if replay, ok, err := service.idempotentReplay("artifact_manifest", tenantID, projectID, options.IdempotencyKey, request); err != nil || ok {
			if err != nil {
				return Envelope[ArtifactManifest]{}, err
			}
			response := replay.(Envelope[ArtifactManifest])
			response.IdempotentReplay = true
			return response, nil
		}
	}

	service.mu.Lock()
	defer service.mu.Unlock()
	if err := service.authorizeAndConsumeLocked(tenantID, projectID, options.APIKeyID, ScopeArtifactManifestWrite, "artifact_manifest", "", 0); err != nil {
		return Envelope[ArtifactManifest]{}, err
	}
	if _, ok := service.runs[runKey(tenantID, projectID, runID)]; !ok {
		return Envelope[ArtifactManifest]{}, NotFoundError{Resource: "run"}
	}
	if err := service.checkUsageQuotaLocked(tenantID, projectID, usageOperationArtifactManifest, 1); err != nil {
		return Envelope[ArtifactManifest]{}, err
	}
	artifactID := options.ArtifactID
	if artifactID == "" {
		artifactID = service.id("artifact", runID)
	}
	now := time.Now().UTC()
	record := ArtifactManifest{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, ArtifactID: artifactID, ManifestSHA256: mustFingerprint(manifest), RawPayloadIncluded: false, APIKeyID: options.APIKeyID, RequestID: options.RequestID, CreatedAt: now}
	service.artifactManifests[artifactManifestKey(tenantID, projectID, runID, artifactID)] = record
	service.recordUsageEventLocked(tenantID, projectID, usageOperationArtifactManifest, 1)
	service.appendAuditEventLocked(tenantID, projectID, "artifact.manifest", runID, options.APIKeyID, options.IdempotencyKey, options.RequestID, JSONMap{"run_id": runID, "artifact_id": artifactID, "manifest_sha256": record.ManifestSHA256}, now)
	response := Envelope[ArtifactManifest]{Operation: "artifact_manifest", Status: "ok", Result: record}
	service.storeIdempotencyLocked("artifact_manifest", tenantID, projectID, options.IdempotencyKey, request, response)
	return response, nil
}

func (service *MemoryService) ListArtifactManifests(tenantID, projectID, runID string) (Envelope[ArtifactManifestList], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	if _, ok := service.runs[runKey(tenantID, projectID, runID)]; !ok {
		return Envelope[ArtifactManifestList]{}, NotFoundError{Resource: "run"}
	}
	manifests := []ArtifactManifest{}
	for _, manifest := range service.artifactManifests {
		if manifest.TenantID == tenantID && manifest.ProjectID == projectID && manifest.RunID == runID {
			manifests = append(manifests, manifest)
		}
	}
	sort.Slice(manifests, func(i, j int) bool {
		if !manifests[i].CreatedAt.Equal(manifests[j].CreatedAt) {
			return manifests[i].CreatedAt.Before(manifests[j].CreatedAt)
		}
		return manifests[i].ArtifactID < manifests[j].ArtifactID
	})
	result := ArtifactManifestList{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, Manifests: manifests, Count: len(manifests)}
	return Envelope[ArtifactManifestList]{Operation: "artifact_manifests", Status: "ok", Result: result}, nil
}

func (service *MemoryService) RunLifecycle(tenantID, projectID, runID string) (Envelope[RunLifecycle], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	run, ok := service.runs[runKey(tenantID, projectID, runID)]
	if !ok {
		return Envelope[RunLifecycle]{}, NotFoundError{Resource: "run"}
	}
	uploads := []RunUpload{}
	for _, upload := range service.runUploads {
		if upload.TenantID == tenantID && upload.ProjectID == projectID && upload.RunID == runID {
			uploads = append(uploads, upload)
		}
	}
	sort.Slice(uploads, func(i, j int) bool {
		if !uploads[i].CreatedAt.Equal(uploads[j].CreatedAt) {
			return uploads[i].CreatedAt.Before(uploads[j].CreatedAt)
		}
		return uploads[i].UploadID < uploads[j].UploadID
	})
	traceBatches := []TraceBatch{}
	for _, batch := range service.traceBatches {
		if batch.TenantID == tenantID && batch.ProjectID == projectID && batch.RunID == runID {
			traceBatches = append(traceBatches, batch)
		}
	}
	sort.Slice(traceBatches, func(i, j int) bool {
		if !traceBatches[i].CreatedAt.Equal(traceBatches[j].CreatedAt) {
			return traceBatches[i].CreatedAt.Before(traceBatches[j].CreatedAt)
		}
		return traceBatches[i].BatchID < traceBatches[j].BatchID
	})
	artifacts := []ArtifactManifest{}
	for _, manifest := range service.artifactManifests {
		if manifest.TenantID == tenantID && manifest.ProjectID == projectID && manifest.RunID == runID {
			artifacts = append(artifacts, manifest)
		}
	}
	sort.Slice(artifacts, func(i, j int) bool {
		if !artifacts[i].CreatedAt.Equal(artifacts[j].CreatedAt) {
			return artifacts[i].CreatedAt.Before(artifacts[j].CreatedAt)
		}
		return artifacts[i].ArtifactID < artifacts[j].ArtifactID
	})
	result := RunLifecycle{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, Run: run, Uploads: uploads, TraceBatches: traceBatches, Artifacts: artifacts, Counts: JSONMap{"uploads": len(uploads), "trace_batches": len(traceBatches), "artifacts": len(artifacts)}, GeneratedAt: time.Now().UTC()}
	return Envelope[RunLifecycle]{Operation: "lifecycle", Status: "ok", Result: result}, nil
}

func (service *MemoryService) UsageSnapshot(tenantID, projectID string) (Envelope[UsageSnapshot], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	totals := map[string]UsageOperationTotal{}
	for _, event := range service.usageEvents {
		if event.TenantID != tenantID || event.ProjectID != projectID {
			continue
		}
		if event.Operation == "" {
			continue
		}
		current := totals[event.Operation]
		current.Operation = event.Operation
		current.Units += event.Units
		current.Events += event.Events
		totals[event.Operation] = current
	}
	operations := make([]string, 0, len(totals))
	for operation := range totals {
		operations = append(operations, operation)
	}
	sort.Strings(operations)
	result := UsageSnapshot{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, GeneratedAt: time.Now().UTC()}
	for _, operation := range operations {
		total := totals[operation]
		result.OperationTotals = append(result.OperationTotals, total)
		result.TotalUnits += total.Units
		result.TotalEvents += total.Events
	}
	return Envelope[UsageSnapshot]{Operation: "usage", Status: "ok", Result: result}, nil
}

func (service *MemoryService) ConfigureUsageQuota(tenantID, projectID, operation string, limit int) (Envelope[UsageOperationTotal], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	operation = normalizeUsageOperation(operation)
	if operation == "" {
		return Envelope[UsageOperationTotal]{}, fmt.Errorf("usage quota operation is required")
	}
	service.usageQuotaLimits[usageQuotaKey(tenantID, projectID, operation)] = limit
	used := service.usageUnitsLocked(tenantID, projectID, operation)
	result := UsageOperationTotal{Operation: operation, Units: used}
	return Envelope[UsageOperationTotal]{Operation: "usage_quota.configure", Status: "ok", Result: result}, nil
}

func (service *MemoryService) AuditLog(tenantID, projectID string, options AuditLogOptions) (Envelope[AuditEventList], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	if _, ok := service.projects[projectKey(tenantID, projectID)]; !ok {
		return Envelope[AuditEventList]{}, NotFoundError{Resource: "project"}
	}
	events := service.auditEventsForProjectLocked(tenantID, projectID)
	filtered := filterAuditEvents(events, options.RunID, options.ActionPrefix, options.Limit)
	result := AuditEventList{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: options.RunID, ActionPrefix: options.ActionPrefix, Events: filtered, Count: len(filtered)}
	return Envelope[AuditEventList]{Operation: "audit_log", Status: "ok", Result: result}, nil
}

func (service *MemoryService) VerifyAuditChain(tenantID, projectID string) (Envelope[AuditChainVerification], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	events := service.auditEventsForProjectLocked(tenantID, projectID)
	result := AuditChainVerification{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, Verified: true, EventCount: len(events), CheckedAt: time.Now().UTC()}
	if len(events) > 0 {
		result.HeadHash = events[0].EventHash
		result.TailHash = events[len(events)-1].EventHash
	}
	return Envelope[AuditChainVerification]{Operation: "audit.chain.verify", Status: "ok", Result: result}, nil
}

func (service *MemoryService) BuildReleaseEvidencePacket(tenantID, projectID, runID string) (Envelope[ReleaseEvidencePacket], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	run, ok := service.runs[runKey(tenantID, projectID, runID)]
	if !ok {
		return Envelope[ReleaseEvidencePacket]{}, NotFoundError{Resource: "run"}
	}
	now := time.Now().UTC()
	verification := service.auditChainVerificationLocked(tenantID, projectID, now)
	packet := ReleaseEvidencePacket{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, PacketID: "release_evidence_" + mustFingerprint(JSONMap{"tenant_id": tenantID, "project_id": projectID, "run_id": runID})[:16], Run: run, Uploads: service.runUploadsForRunLocked(tenantID, projectID, runID), TraceBatches: service.traceBatchesForRunLocked(tenantID, projectID, runID), ArtifactManifests: service.artifactManifestsForRunLocked(tenantID, projectID, runID), AuditVerification: verification, GeneratedAt: now}
	packet.PacketSHA256 = releaseEvidencePacketSHA(packet)
	return Envelope[ReleaseEvidencePacket]{Operation: "release_evidence", Status: "ok", Result: packet}, nil
}

func (service *MemoryService) VerifyReleaseEvidencePacket(tenantID, projectID, runID string, packet JSONMap) (Envelope[ReleaseEvidenceVerification], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	result := verifyReleaseEvidencePacketMap(tenantID, projectID, runID, packet, time.Now().UTC())
	return Envelope[ReleaseEvidenceVerification]{Operation: "release_evidence.verify", Status: "ok", Result: result}, nil
}

func (service *MemoryService) CreateAPIKey(tenantID, projectID string, options CreateAPIKeyOptions) (Envelope[APIKeyCreateResult], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	if _, ok := service.projects[projectKey(tenantID, projectID)]; !ok {
		return Envelope[APIKeyCreateResult]{}, NotFoundError{Resource: "project"}
	}
	if strings.TrimSpace(options.APIKey) != "" {
		return Envelope[APIKeyCreateResult]{}, AuthzError{Code: "secret_input_rejected", Message: "local API key lifecycle only generates one-time local test secrets"}
	}
	keyID := strings.TrimSpace(firstNonEmpty(options.KeyID, options.AuthKeyID))
	if keyID == "" {
		keyID = service.id("key", options.Name)
	}
	if stringHasRawSecretShape(keyID) || stringHasRawSecretShape(options.Name) {
		return Envelope[APIKeyCreateResult]{}, AuthzError{Code: "secret_input_rejected", Message: "api key identifiers and names must not contain raw secret material"}
	}
	storageKey := apiKeyRecordKey(tenantID, projectID, keyID)
	if _, exists := service.apiKeys[storageKey]; exists {
		return Envelope[APIKeyCreateResult]{}, fmt.Errorf("api key %s already exists", keyID)
	}
	scopes := sortedUniqueStrings(options.Scopes)
	if len(scopes) == 0 {
		return Envelope[APIKeyCreateResult]{}, fmt.Errorf("at least one scope is required")
	}
	secret := localAPIKeySecretPrefix + keyID + "_" + mustFingerprint(JSONMap{"tenant_id": tenantID, "project_id": projectID, "key_id": keyID})[:16]
	now := time.Now().UTC()
	record := APIKeyRecord{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, Name: strings.TrimSpace(options.Name), SecretPrefix: secretPrefix(secret), SecretSHA256: secretHash(secret), Scopes: scopes, CreatedAt: now}
	service.apiKeys[storageKey] = record
	result := APIKeyCreateResult{SchemaVersion: ControlPlaneSchemaVersion, APIKey: redactedAPIKeyRecord(record), OneTimeSecretDisplayed: options.RevealSecret}
	if options.RevealSecret {
		result.OneTimeSecret = secret
	}
	return Envelope[APIKeyCreateResult]{Operation: "api_key.create", Status: "ok", Result: result}, nil
}

func (service *MemoryService) ListAPIKeys(tenantID, projectID string) (Envelope[APIKeyListResult], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	keys := make([]APIKeyRecord, 0)
	for _, record := range service.apiKeys {
		if record.TenantID == tenantID && record.ProjectID == projectID {
			keys = append(keys, redactedAPIKeyRecord(record))
		}
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i].KeyID < keys[j].KeyID })
	result := APIKeyListResult{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, APIKeys: keys, Count: len(keys)}
	return Envelope[APIKeyListResult]{Operation: "api_key.list", Status: "ok", Result: result}, nil
}

func (service *MemoryService) RevokeAPIKey(tenantID, projectID, keyID string) (Envelope[APIKeyRecord], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	storageKey := apiKeyRecordKey(tenantID, projectID, keyID)
	record, ok := service.apiKeys[storageKey]
	if !ok {
		return Envelope[APIKeyRecord]{}, NotFoundError{Resource: "api key"}
	}
	record.Revoked = true
	service.apiKeys[storageKey] = record
	return Envelope[APIKeyRecord]{Operation: "api_key.revoke", Status: "ok", Result: redactedAPIKeyRecord(record)}, nil
}

func (service *MemoryService) VerifyAPIKeySecret(tenantID, projectID, keyID, secret, scope string) (Envelope[APIKeyVerifyResult], error) {
	if !strings.HasPrefix(strings.TrimSpace(secret), localAPIKeySecretPrefix) {
		return Envelope[APIKeyVerifyResult]{}, AuthzError{Code: "secret_input_rejected", Message: "local verification accepts generated local test secrets only"}
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	storageKey := apiKeyRecordKey(tenantID, projectID, keyID)
	record, ok := service.apiKeys[storageKey]
	if !ok {
		return Envelope[APIKeyVerifyResult]{}, NotFoundError{Resource: "api key"}
	}
	authenticated := strings.TrimSpace(secret) != "" && secretHash(secret) == record.SecretSHA256 && !record.Revoked && scopeAllowed(record.Scopes, scope)
	if authenticated {
		now := time.Now().UTC()
		record.LastUsedAt = &now
		service.apiKeys[storageKey] = record
	}
	result := APIKeyVerifyResult{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, Authenticated: authenticated, Scope: scope, SecretValuePresent: false, APIKey: redactedAPIKeyRecord(record)}
	return Envelope[APIKeyVerifyResult]{Operation: "api_key.verify", Status: "ok", Result: result}, nil
}

func (service *MemoryService) ConfigureAPIKeyRateLimit(tenantID, projectID, keyID, operation string, limit int) (Envelope[APIKeyRateLimit], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	if _, ok := service.apiKeys[apiKeyRecordKey(tenantID, projectID, keyID)]; !ok {
		return Envelope[APIKeyRateLimit]{}, NotFoundError{Resource: "api key"}
	}
	if strings.TrimSpace(operation) == "" {
		return Envelope[APIKeyRateLimit]{}, fmt.Errorf("operation is required")
	}
	if limit < 0 {
		return Envelope[APIKeyRateLimit]{}, fmt.Errorf("limit must be non-negative")
	}
	now := time.Now().UTC()
	quota := service.apiKeyRateLimitLocked(tenantID, projectID, keyID, operation, now)
	quota.Limit = limit
	quota.Remaining = limit - quota.Used
	if quota.Remaining < 0 {
		quota.Remaining = 0
	}
	quota.UpdatedAt = now
	service.apiKeyRateLimits[apiKeyQuotaKey(tenantID, projectID, keyID, operation)] = quota
	return Envelope[APIKeyRateLimit]{Operation: "api_key.rate_limit.configure", Status: "ok", Result: quota}, nil
}

func (service *MemoryService) APIKeyRateLimitSnapshot(tenantID, projectID, keyID string) (Envelope[APIKeyRateLimitSnapshot], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	limits := make([]APIKeyRateLimit, 0)
	for _, quota := range service.apiKeyRateLimits {
		if quota.TenantID == tenantID && quota.ProjectID == projectID && (keyID == "" || quota.KeyID == keyID) {
			limits = append(limits, quota)
		}
	}
	sort.Slice(limits, func(i, j int) bool {
		if limits[i].KeyID != limits[j].KeyID {
			return limits[i].KeyID < limits[j].KeyID
		}
		return limits[i].Operation < limits[j].Operation
	})
	result := APIKeyRateLimitSnapshot{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, RateLimits: limits, Count: len(limits)}
	return Envelope[APIKeyRateLimitSnapshot]{Operation: "api_key.rate_limit.snapshot", Status: "ok", Result: result}, nil
}

func (service *MemoryService) PreflightAPIKey(options PreflightOptions) (Envelope[AuthPreflight], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	result, err := service.preflightAPIKeyLocked(options, time.Now().UTC())
	return Envelope[AuthPreflight]{Operation: "api_key.preflight", Status: "ok", Result: result}, err
}

type EnqueueWorkerJobOptions struct {
	JobID          string
	Priority       int
	MaxAttempts    int
	APIKeyID       string
	IdempotencyKey string
	RequestID      string
}

type LeaseWorkerJobOptions struct {
	LeaseSeconds int
	JobType      string
	APIKeyID     string
	RequestID    string
}

type CompleteWorkerJobOptions struct {
	APIKeyID  string
	RequestID string
}

type FailWorkerJobOptions struct {
	RetryAfterSeconds *int
	APIKeyID          string
	RequestID         string
}

type ListWorkerJobsOptions struct {
	Status    string
	JobType   string
	Limit     int
	AuthKeyID string
}

func (service *MemoryService) EnqueueWorkerJob(tenantID, projectID, jobType, targetID string, payload JSONMap, options EnqueueWorkerJobOptions) (Envelope[WorkerJob], error) {
	normalizedPayload := cloneMap(payload)
	request := JSONMap{"tenant_id": tenantID, "project_id": projectID, "job_type": jobType, "target_id": targetID, "payload": normalizedPayload, "job_id": options.JobID, "priority": options.Priority, "max_attempts": options.MaxAttempts, "api_key_id": options.APIKeyID}
	if options.IdempotencyKey != "" {
		if replay, ok, err := service.idempotentReplay("worker.job.enqueue", tenantID, projectID, options.IdempotencyKey, request); err != nil || ok {
			if err != nil {
				return Envelope[WorkerJob]{}, err
			}
			result := replay.(Envelope[WorkerJob])
			result.IdempotentReplay = true
			return result, nil
		}
	}

	if strings.TrimSpace(jobType) == "" {
		return Envelope[WorkerJob]{}, fmt.Errorf("job_type is required")
	}
	maxAttempts := options.MaxAttempts
	if maxAttempts == 0 {
		maxAttempts = 3
	}
	if maxAttempts < 1 {
		return Envelope[WorkerJob]{}, fmt.Errorf("max_attempts must be positive")
	}
	priority := options.Priority
	if priority == 0 {
		priority = 100
	}
	payloadSHA, err := fingerprint(normalizedPayload)
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}

	service.mu.Lock()
	defer service.mu.Unlock()
	if _, ok := service.projects[projectKey(tenantID, projectID)]; !ok {
		return Envelope[WorkerJob]{}, NotFoundError{Resource: "project"}
	}
	jobID := options.JobID
	if jobID == "" {
		jobID = service.id("job", jobType)
	}
	if _, exists := service.workerJobs[jobID]; exists {
		return Envelope[WorkerJob]{}, fmt.Errorf("worker job already exists: %s", jobID)
	}
	now := time.Now().UTC()
	availableAt := now
	job := WorkerJob{SchemaVersion: ControlPlaneSchemaVersion, JobID: jobID, TenantID: tenantID, ProjectID: projectID, JobType: jobType, TargetID: targetID, PayloadSHA256: payloadSHA, RawPayloadIncluded: false, Status: WorkerJobStatusQueued, Priority: priority, Attempts: 0, MaxAttempts: maxAttempts, AvailableAt: &availableAt, IdempotencyKey: options.IdempotencyKey, RequestID: options.RequestID, CreatedAt: now, UpdatedAt: now}
	service.workerJobs[job.JobID] = job
	service.recordAPIKeyUsageLocked(tenantID, projectID, options.APIKeyID, "worker.job.enqueue", 1, now)
	service.recordUsageEventLocked(tenantID, projectID, "worker.job.enqueue", 1)
	response := Envelope[WorkerJob]{Operation: "worker.job.enqueue", Status: "ok", Result: job}
	service.storeIdempotencyLocked("worker.job.enqueue", tenantID, projectID, options.IdempotencyKey, request, response)
	return response, nil
}

func (service *MemoryService) LeaseWorkerJob(tenantID, projectID, leaseOwnerID string, options LeaseWorkerJobOptions) (Envelope[WorkerLeaseResult], error) {
	if strings.TrimSpace(leaseOwnerID) == "" {
		return Envelope[WorkerLeaseResult]{}, fmt.Errorf("lease_owner_id is required")
	}
	leaseSeconds := options.LeaseSeconds
	if leaseSeconds == 0 {
		leaseSeconds = 300
	}
	if leaseSeconds < 1 {
		return Envelope[WorkerLeaseResult]{}, fmt.Errorf("lease_seconds must be positive")
	}

	service.mu.Lock()
	defer service.mu.Unlock()
	if _, ok := service.projects[projectKey(tenantID, projectID)]; !ok {
		return Envelope[WorkerLeaseResult]{}, NotFoundError{Resource: "project"}
	}
	now := time.Now().UTC()
	service.expireLeasesLocked(now)
	candidates := make([]WorkerJob, 0)
	for _, job := range service.workerJobs {
		if job.TenantID != tenantID || job.ProjectID != projectID {
			continue
		}
		if options.JobType != "" && job.JobType != options.JobType {
			continue
		}
		if !workerJobAvailableForLease(job, now) {
			continue
		}
		candidates = append(candidates, job)
	}
	sort.Slice(candidates, func(i, j int) bool {
		return workerJobLess(candidates[i], candidates[j])
	})
	if len(candidates) == 0 {
		result := WorkerLeaseResult{SchemaVersion: ControlPlaneSchemaVersion, Status: "empty", TenantID: tenantID, ProjectID: projectID, Leased: false, Job: nil, CreatedAt: now}
		return Envelope[WorkerLeaseResult]{Operation: "worker.job.lease", Status: "ok", Result: result}, nil
	}
	job := candidates[0]
	leaseExpiresAt := now.Add(time.Duration(leaseSeconds) * time.Second)
	job.Status = WorkerJobStatusLeased
	job.Attempts++
	job.LeaseOwnerID = leaseOwnerID
	job.LeaseExpiresAt = &leaseExpiresAt
	job.UpdatedAt = now
	service.workerJobs[job.JobID] = job
	service.recordAPIKeyUsageLocked(tenantID, projectID, options.APIKeyID, "worker.job.lease", 1, now)
	service.recordUsageEventLocked(tenantID, projectID, "worker.job.lease", 1)
	resultJob := job
	result := WorkerLeaseResult{SchemaVersion: ControlPlaneSchemaVersion, Status: "leased", TenantID: tenantID, ProjectID: projectID, Leased: true, Job: &resultJob}
	return Envelope[WorkerLeaseResult]{Operation: "worker.job.lease", Status: "ok", Result: result}, nil
}

func (service *MemoryService) HeartbeatWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, leaseSeconds int) (Envelope[WorkerJob], error) {
	if leaseSeconds == 0 {
		leaseSeconds = 300
	}
	if leaseSeconds < 1 {
		return Envelope[WorkerJob]{}, fmt.Errorf("lease_seconds must be positive")
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	now := time.Now().UTC()
	job, err := service.workerJobRecordLocked(tenantID, projectID, jobID, now)
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	if err := requireWorkerJobLease(job, leaseOwnerID); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	leaseExpiresAt := now.Add(time.Duration(leaseSeconds) * time.Second)
	job.LeaseExpiresAt = &leaseExpiresAt
	job.UpdatedAt = now
	service.workerJobs[job.JobID] = job
	return Envelope[WorkerJob]{Operation: "worker.job.heartbeat", Status: "ok", Result: job}, nil
}

func (service *MemoryService) CompleteWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, result JSONMap, options CompleteWorkerJobOptions) (Envelope[WorkerJob], error) {
	resultSHA, err := fingerprint(cloneMap(result))
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	now := time.Now().UTC()
	job, err := service.workerJobRecordLocked(tenantID, projectID, jobID, now)
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	if err := requireWorkerJobLease(job, leaseOwnerID); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	job.Status = WorkerJobStatusCompleted
	job.LeaseOwnerID = ""
	job.LeaseExpiresAt = nil
	job.ResultSHA256 = resultSHA
	job.UpdatedAt = now
	job.CompletedAt = &now
	service.workerJobs[job.JobID] = job
	service.recordAPIKeyUsageLocked(tenantID, projectID, options.APIKeyID, "worker.job.complete", 1, now)
	service.recordUsageEventLocked(tenantID, projectID, "worker.job.complete", 1)
	return Envelope[WorkerJob]{Operation: "worker.job.complete", Status: "ok", Result: job}, nil
}

func (service *MemoryService) FailWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, failure JSONMap, options FailWorkerJobOptions) (Envelope[WorkerJob], error) {
	failure = cloneMap(failure)
	failureSHA, err := fingerprint(failure)
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	service.mu.Lock()
	defer service.mu.Unlock()
	now := time.Now().UTC()
	job, err := service.workerJobRecordLocked(tenantID, projectID, jobID, now)
	if err != nil {
		return Envelope[WorkerJob]{}, err
	}
	if err := requireWorkerJobLease(job, leaseOwnerID); err != nil {
		return Envelope[WorkerJob]{}, err
	}
	errorType, _ := failure["type"].(string)
	if strings.TrimSpace(errorType) == "" {
		errorType = "worker_error"
	}
	message, _ := failure["message"].(string)
	if strings.TrimSpace(message) == "" {
		message = "redacted"
	}
	job.LastError = &WorkerJobError{SHA256: failureSHA, Type: errorType, Message: message, RawPayloadIncluded: false, FailedAt: now}
	job.LeaseOwnerID = ""
	job.LeaseExpiresAt = nil
	if job.Attempts >= job.MaxAttempts {
		job.Status = WorkerJobStatusDeadLettered
		job.DeadLetteredAt = &now
		job.AvailableAt = nil
	} else {
		job.Status = WorkerJobStatusRetrying
		retrySeconds := retryAfterSeconds(job.Attempts, options.RetryAfterSeconds)
		availableAt := now.Add(time.Duration(retrySeconds) * time.Second)
		job.AvailableAt = &availableAt
	}
	job.UpdatedAt = now
	service.workerJobs[job.JobID] = job
	service.recordAPIKeyUsageLocked(tenantID, projectID, options.APIKeyID, "worker.job.fail", 1, now)
	service.recordUsageEventLocked(tenantID, projectID, "worker.job.fail", 1)
	return Envelope[WorkerJob]{Operation: "worker.job.fail", Status: "ok", Result: job}, nil
}

func (service *MemoryService) ListWorkerJobs(tenantID, projectID string, options ListWorkerJobsOptions) (Envelope[WorkerJobList], error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	if _, ok := service.projects[projectKey(tenantID, projectID)]; !ok {
		return Envelope[WorkerJobList]{}, NotFoundError{Resource: "project"}
	}
	now := time.Now().UTC()
	service.expireLeasesLocked(now)
	jobs := make([]WorkerJob, 0)
	for _, job := range service.workerJobs {
		if job.TenantID != tenantID || job.ProjectID != projectID {
			continue
		}
		if options.Status != "" && job.Status != options.Status {
			continue
		}
		if options.JobType != "" && job.JobType != options.JobType {
			continue
		}
		jobs = append(jobs, job)
	}
	sort.Slice(jobs, func(i, j int) bool { return workerJobLess(jobs[i], jobs[j]) })
	if options.Limit > 0 && options.Limit < len(jobs) {
		jobs = jobs[:options.Limit]
	}
	filters := JSONMap{"status": options.Status, "job_type": options.JobType, "limit": options.Limit}
	result := WorkerJobList{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, Filters: filters, Jobs: jobs, Count: len(jobs)}
	return Envelope[WorkerJobList]{Operation: "worker.job.list", Status: "ok", Result: result}, nil
}

func (service *MemoryService) idempotentReplay(operation, tenantID, projectID, key string, request any) (any, bool, error) {
	service.mu.Lock()
	defer service.mu.Unlock()
	ledgerKey := idempotencyLedgerKey(operation, tenantID, projectID, key)
	record, ok := service.idem[ledgerKey]
	if !ok {
		return nil, false, nil
	}
	fingerprint, err := fingerprint(request)
	if err != nil {
		return nil, false, err
	}
	if record.Fingerprint != fingerprint {
		return nil, false, IdempotencyConflictError{Operation: operation, Key: key}
	}
	return record.Response, true, nil
}

func (service *MemoryService) storeIdempotencyLocked(operation, tenantID, projectID, key string, request any, response any) {
	if key == "" {
		return
	}
	service.idem[idempotencyLedgerKey(operation, tenantID, projectID, key)] = idemRecord{Fingerprint: mustFingerprint(request), Response: response}
}

func (service *MemoryService) id(prefix, name string) string {
	service.nextID++
	stem := strings.Trim(strings.ToLower(name), " _-")
	stem = strings.ReplaceAll(stem, " ", "_")
	if stem == "" {
		stem = "local"
	}
	return fmt.Sprintf("%s_%s_%d", prefix, stem, service.nextID)
}

func (service *MemoryService) localAPIKeyChecksEnabledLocked() bool {
	return len(service.apiKeys) > 0
}

func (service *MemoryService) authorizeAndConsumeLocked(tenantID, projectID, keyID, scope, operation, usageOperation string, units int) error {
	now := time.Now().UTC()
	if _, err := service.preflightAPIKeyLocked(PreflightOptions{TenantID: tenantID, ProjectID: projectID, KeyID: keyID, Scope: scope, Operation: operation, Units: units}, now); err != nil {
		return err
	}
	if err := service.checkUsageQuotaLocked(tenantID, projectID, usageOperation, units); err != nil {
		return err
	}
	service.recordAPIKeyUsageLocked(tenantID, projectID, keyID, operation, units, now)
	service.recordUsageEventLocked(tenantID, projectID, usageOperation, units)
	return nil
}

const (
	usageOperationSubmit           = "sdk.submit"
	usageOperationRunUpload        = "run.upload"
	usageOperationTraceIngest      = "trace.ingest"
	usageOperationArtifactManifest = "artifact.manifest"
)

func (service *MemoryService) checkUsageQuotaLocked(tenantID, projectID, operation string, units int) error {
	operation = normalizeUsageOperation(operation)
	if operation == "" {
		return nil
	}
	if units <= 0 {
		units = 1
	}
	limit, ok := service.usageQuotaLimits[usageQuotaKey(tenantID, projectID, operation)]
	if !ok || limit < 0 {
		return nil
	}
	used := service.usageUnitsLocked(tenantID, projectID, operation)
	if used+units > limit {
		return QuotaExceededError{Operation: operation, Limit: limit, Used: used, Requested: units}
	}
	return nil
}

func (service *MemoryService) usageUnitsLocked(tenantID, projectID, operation string) int {
	operation = normalizeUsageOperation(operation)
	used := 0
	for _, event := range service.usageEvents {
		if event.TenantID == tenantID && event.ProjectID == projectID && event.Operation == operation {
			used += event.Units
		}
	}
	return used
}

func (service *MemoryService) recordUsageEventLocked(tenantID, projectID, operation string, units int) {
	operation = normalizeUsageOperation(operation)
	if operation == "" {
		return
	}
	if units <= 0 {
		units = 1
	}
	service.usageEvents = append(service.usageEvents, usageEvent{TenantID: tenantID, ProjectID: projectID, Operation: operation, Units: units, Events: 1})
}

func normalizeUsageOperation(operation string) string {
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

func usageQuotaKey(tenantID, projectID, operation string) string {
	return tenantID + "/" + projectID + "/" + normalizeUsageOperation(operation)
}

func (service *MemoryService) preflightAPIKeyLocked(options PreflightOptions, now time.Time) (AuthPreflight, error) {
	units := options.Units
	if units <= 0 {
		units = 1
	}
	result := AuthPreflight{SchemaVersion: ControlPlaneSchemaVersion, TenantID: options.TenantID, ProjectID: options.ProjectID, KeyID: options.KeyID, Operation: options.Operation, CheckedAt: now}
	if !service.localAPIKeyChecksEnabledLocked() {
		result.Allowed = true
		return result, nil
	}
	record, ok := service.apiKeys[apiKeyRecordKey(options.TenantID, options.ProjectID, options.KeyID)]
	if !ok {
		return result, AuthzError{Code: "api_key_not_found", Message: "api key handle not found"}
	}
	result.Scopes = append([]string(nil), record.Scopes...)
	if record.Revoked {
		return result, AuthzError{Code: "api_key_revoked", Message: "api key handle has been revoked"}
	}
	if !scopeAllowed(record.Scopes, options.Scope) {
		return result, AuthzError{Code: "scope_denied", Message: "api key handle does not grant required scope"}
	}
	if quota, ok := service.apiKeyRateLimits[apiKeyQuotaKey(options.TenantID, options.ProjectID, options.KeyID, options.Operation)]; ok {
		quota.Remaining = quota.Limit - quota.Used
		if quota.Remaining < 0 {
			quota.Remaining = 0
		}
		result.Quota = &quota
		if quota.Limit >= 0 && quota.Used+units > quota.Limit {
			return result, QuotaExceededError{Operation: options.Operation, Limit: quota.Limit, Used: quota.Used}
		}
	}
	result.Allowed = true
	return result, nil
}

func (service *MemoryService) recordAPIKeyUsageLocked(tenantID, projectID, keyID, operation string, units int, now time.Time) {
	if keyID == "" || operation == "" {
		return
	}
	if units <= 0 {
		units = 1
	}
	quotaKey := apiKeyQuotaKey(tenantID, projectID, keyID, operation)
	quota, ok := service.apiKeyRateLimits[quotaKey]
	if ok {
		quota.Used += units
		quota.Remaining = quota.Limit - quota.Used
		if quota.Remaining < 0 {
			quota.Remaining = 0
		}
		quota.UpdatedAt = now
		service.apiKeyRateLimits[quotaKey] = quota
	}
	if record, ok := service.apiKeys[apiKeyRecordKey(tenantID, projectID, keyID)]; ok {
		record.LastUsedAt = &now
		service.apiKeys[apiKeyRecordKey(tenantID, projectID, keyID)] = record
	}
}

func (service *MemoryService) apiKeyRateLimitLocked(tenantID, projectID, keyID, operation string, now time.Time) APIKeyRateLimit {
	if quota, ok := service.apiKeyRateLimits[apiKeyQuotaKey(tenantID, projectID, keyID, operation)]; ok {
		return quota
	}
	return APIKeyRateLimit{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, KeyID: keyID, Operation: operation, Remaining: 0, UpdatedAt: now}
}

func apiKeyRecordKey(tenantID, projectID, keyID string) string {
	return tenantID + "/" + projectID + "/" + keyID
}

func apiKeyQuotaKey(tenantID, projectID, keyID, operation string) string {
	return apiKeyRecordKey(tenantID, projectID, keyID) + "/" + operation
}

func scopeAllowed(scopes []string, required string) bool {
	if strings.TrimSpace(required) == "" {
		return true
	}
	for _, scope := range scopes {
		if scope == "*" || scope == required {
			return true
		}
	}
	return false
}

func sortedUniqueStrings(values []string) []string {
	seen := map[string]struct{}{}
	output := []string{}
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		output = append(output, trimmed)
	}
	sort.Strings(output)
	return output
}

func redactedAPIKeyRecord(record APIKeyRecord) APIKeyRecord {
	record.SecretSHA256 = ""
	return record
}

func secretPrefix(secret string) string {
	if len(secret) <= 8 {
		return secret
	}
	return secret[:8]
}

func secretHash(secret string) string {
	digest := sha256.Sum256([]byte(secret))
	return hex.EncodeToString(digest[:])
}

func stringHasRawSecretShape(value string) bool {
	trimmed := strings.TrimSpace(value)
	return strings.HasPrefix(trimmed, "sk-") || strings.HasPrefix(trimmed, "ashr_")
}

func fingerprint(value any) (string, error) {
	payload, err := stableJSON(value)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:]), nil
}

func mustFingerprint(value any) string {
	fingerprint, err := fingerprint(value)
	if err != nil {
		panic(err)
	}
	return fingerprint
}

func releaseEvidencePacketSHA(packet ReleaseEvidencePacket) string {
	copy := packet
	copy.PacketSHA256 = ""
	mapped, err := jsonMapFromStruct(copy)
	if err != nil {
		panic(err)
	}
	return releaseEvidencePacketMapSHA(mapped)
}

func releaseEvidencePacketMapSHA(packet JSONMap) string {
	copy := cloneMap(packet)
	copy["packet_sha256"] = ""
	return mustFingerprint(copy)
}

func idempotencyLedgerKey(operation, tenantID, projectID, key string) string {
	return operation + "\x00" + tenantID + "\x00" + projectID + "\x00" + key
}

func projectKey(tenantID, projectID string) string { return tenantID + "/" + projectID }
func datasetKey(tenantID, projectID, datasetID string) string {
	return tenantID + "/" + projectID + "/" + datasetID
}
func runKey(tenantID, projectID, runID string) string {
	return tenantID + "/" + projectID + "/" + runID
}
func runUploadKey(tenantID, projectID, runID, uploadID string) string {
	return runKey(tenantID, projectID, runID) + "/" + uploadID
}
func traceBatchKey(tenantID, projectID, runID, batchID string) string {
	return runKey(tenantID, projectID, runID) + "/" + batchID
}
func artifactManifestKey(tenantID, projectID, runID, artifactID string) string {
	return runKey(tenantID, projectID, runID) + "/" + artifactID
}

func (service *MemoryService) appendAuditEventLocked(tenantID, projectID, action, targetID, apiKeyID, idempotencyKey, requestID string, after JSONMap, now time.Time) AuditEvent {
	now = now.UTC()
	previousHash := ""
	for index := len(service.auditEvents) - 1; index >= 0; index-- {
		event := service.auditEvents[index]
		if event.TenantID == tenantID && event.ProjectID == projectID {
			previousHash = event.EventHash
			break
		}
	}
	event := AuditEvent{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, AuditEventID: service.id("audit", action), Action: action, TargetID: targetID, APIKeyID: apiKeyID, IdempotencyKey: idempotencyKey, RequestID: requestID, PreviousHash: previousHash, After: defaultJSONMap(after), CreatedAt: now, CreatedAtUnixNS: now.UnixNano()}
	event.EventHash = mustFingerprint(JSONMap{"tenant_id": event.TenantID, "project_id": event.ProjectID, "audit_event_id": event.AuditEventID, "action": event.Action, "target_id": event.TargetID, "api_key_id": event.APIKeyID, "idempotency_key": event.IdempotencyKey, "request_id": event.RequestID, "previous_hash": event.PreviousHash, "after": event.After, "created_at_unixns": event.CreatedAtUnixNS})
	service.auditEvents = append(service.auditEvents, event)
	return event
}

func (service *MemoryService) auditEventsForProjectLocked(tenantID, projectID string) []AuditEvent {
	events := []AuditEvent{}
	for _, event := range service.auditEvents {
		if event.TenantID == tenantID && event.ProjectID == projectID {
			events = append(events, event)
		}
	}
	sortAuditEvents(events)
	return events
}

func (service *MemoryService) auditChainVerificationLocked(tenantID, projectID string, checkedAt time.Time) AuditChainVerification {
	events := service.auditEventsForProjectLocked(tenantID, projectID)
	result := AuditChainVerification{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, Verified: true, EventCount: len(events), CheckedAt: checkedAt}
	if len(events) > 0 {
		result.HeadHash = events[0].EventHash
		result.TailHash = events[len(events)-1].EventHash
	}
	return result
}

func (service *MemoryService) runUploadsForRunLocked(tenantID, projectID, runID string) []RunUpload {
	uploads := []RunUpload{}
	for _, upload := range service.runUploads {
		if upload.TenantID == tenantID && upload.ProjectID == projectID && upload.RunID == runID {
			uploads = append(uploads, upload)
		}
	}
	sort.Slice(uploads, func(i, j int) bool {
		if !uploads[i].CreatedAt.Equal(uploads[j].CreatedAt) {
			return uploads[i].CreatedAt.Before(uploads[j].CreatedAt)
		}
		return uploads[i].UploadID < uploads[j].UploadID
	})
	return uploads
}

func (service *MemoryService) traceBatchesForRunLocked(tenantID, projectID, runID string) []TraceBatch {
	batches := []TraceBatch{}
	for _, batch := range service.traceBatches {
		if batch.TenantID == tenantID && batch.ProjectID == projectID && batch.RunID == runID {
			batches = append(batches, batch)
		}
	}
	sort.Slice(batches, func(i, j int) bool {
		if !batches[i].CreatedAt.Equal(batches[j].CreatedAt) {
			return batches[i].CreatedAt.Before(batches[j].CreatedAt)
		}
		return batches[i].BatchID < batches[j].BatchID
	})
	return batches
}

func (service *MemoryService) artifactManifestsForRunLocked(tenantID, projectID, runID string) []ArtifactManifest {
	manifests := []ArtifactManifest{}
	for _, manifest := range service.artifactManifests {
		if manifest.TenantID == tenantID && manifest.ProjectID == projectID && manifest.RunID == runID {
			manifests = append(manifests, manifest)
		}
	}
	sort.Slice(manifests, func(i, j int) bool {
		if !manifests[i].CreatedAt.Equal(manifests[j].CreatedAt) {
			return manifests[i].CreatedAt.Before(manifests[j].CreatedAt)
		}
		return manifests[i].ArtifactID < manifests[j].ArtifactID
	})
	return manifests
}

func filterAuditEvents(events []AuditEvent, runID, actionPrefix string, limit int) []AuditEvent {
	filtered := []AuditEvent{}
	for _, event := range events {
		if runID != "" && event.TargetID != runID && stringFromAny(event.After["run_id"]) != runID {
			continue
		}
		if actionPrefix != "" && !strings.HasPrefix(event.Action, actionPrefix) {
			continue
		}
		filtered = append(filtered, event)
	}
	if limit > 0 && len(filtered) > limit {
		filtered = filtered[len(filtered)-limit:]
	}
	return filtered
}

func sortAuditEvents(events []AuditEvent) {
	sort.Slice(events, func(i, j int) bool {
		if !events[i].CreatedAt.Equal(events[j].CreatedAt) {
			return events[i].CreatedAt.Before(events[j].CreatedAt)
		}
		return events[i].AuditEventID < events[j].AuditEventID
	})
}

func verifyReleaseEvidencePacketMap(tenantID, projectID, runID string, packet JSONMap, checkedAt time.Time) ReleaseEvidenceVerification {
	result := ReleaseEvidenceVerification{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, PacketID: stringFromAny(packet["packet_id"]), CheckedAt: checkedAt}
	for _, field := range []string{"schema_version", "tenant_id", "project_id", "run_id", "packet_id", "packet_sha256"} {
		if stringFromAny(packet[field]) == "" {
			result.Reason = field + " is required"
			return result
		}
	}
	if stringFromAny(packet["tenant_id"]) != tenantID || stringFromAny(packet["project_id"]) != projectID || stringFromAny(packet["run_id"]) != runID {
		result.Reason = "packet scope does not match requested tenant/project/run"
		return result
	}
	packetSHA := stringFromAny(packet["packet_sha256"])
	computed := releaseEvidencePacketMapSHA(packet)
	result.PacketSHA256 = computed
	if computed != packetSHA {
		result.Reason = "packet_sha256 mismatch"
		return result
	}
	verification := jsonMapFromAny(packet["audit_verification"])
	verified, ok := verification["verified"].(bool)
	if !ok || !verified {
		result.Reason = "audit_verification.verified must be true"
		return result
	}
	result.Verified = true
	return result
}

func jsonMapFromStruct(value any) (JSONMap, error) {
	payload, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	var mapped JSONMap
	if err := json.Unmarshal(payload, &mapped); err != nil {
		return nil, err
	}
	return mapped, nil
}

func defaultJSONMap(value JSONMap) JSONMap {
	if value == nil {
		return JSONMap{}
	}
	return value
}

func (service *MemoryService) workerJobRecordLocked(tenantID, projectID, jobID string, now time.Time) (WorkerJob, error) {
	job, ok := service.workerJobs[jobID]
	if !ok || job.TenantID != tenantID || job.ProjectID != projectID {
		return WorkerJob{}, NotFoundError{Resource: "worker job"}
	}
	if job.Status == WorkerJobStatusLeased && job.LeaseExpiresAt != nil && !job.LeaseExpiresAt.After(now) {
		job.Status = WorkerJobStatusRetrying
		job.LeaseOwnerID = ""
		job.LeaseExpiresAt = nil
		availableAt := now
		job.AvailableAt = &availableAt
		job.UpdatedAt = now
		service.workerJobs[job.JobID] = job
	}
	return job, nil
}

func (service *MemoryService) expireLeasesLocked(now time.Time) {
	for jobID, job := range service.workerJobs {
		if job.Status != WorkerJobStatusLeased || job.LeaseExpiresAt == nil || job.LeaseExpiresAt.After(now) {
			continue
		}
		job.Status = WorkerJobStatusRetrying
		job.LeaseOwnerID = ""
		job.LeaseExpiresAt = nil
		availableAt := now
		job.AvailableAt = &availableAt
		job.UpdatedAt = now
		service.workerJobs[jobID] = job
	}
}

func workerJobAvailableForLease(job WorkerJob, now time.Time) bool {
	switch job.Status {
	case WorkerJobStatusQueued, WorkerJobStatusRetrying:
		return job.AvailableAt == nil || !job.AvailableAt.After(now)
	case WorkerJobStatusLeased:
		return job.LeaseExpiresAt != nil && !job.LeaseExpiresAt.After(now)
	default:
		return false
	}
}

func workerJobLess(left, right WorkerJob) bool {
	if left.Priority != right.Priority {
		return left.Priority < right.Priority
	}
	leftAvailable, rightAvailable := sortableTime(left.AvailableAt), sortableTime(right.AvailableAt)
	if !leftAvailable.Equal(rightAvailable) {
		return leftAvailable.Before(rightAvailable)
	}
	if !left.CreatedAt.Equal(right.CreatedAt) {
		return left.CreatedAt.Before(right.CreatedAt)
	}
	return left.JobID < right.JobID
}

func sortableTime(value *time.Time) time.Time {
	if value == nil {
		return time.Time{}
	}
	return *value
}

func requireWorkerJobLease(job WorkerJob, leaseOwnerID string) error {
	if strings.TrimSpace(leaseOwnerID) == "" {
		return fmt.Errorf("lease_owner_id is required")
	}
	if job.Status != WorkerJobStatusLeased || job.LeaseOwnerID != leaseOwnerID || job.LeaseExpiresAt == nil || !job.LeaseExpiresAt.After(time.Now().UTC()) {
		return fmt.Errorf("worker job is not leased by %s", leaseOwnerID)
	}
	return nil
}

func retryAfterSeconds(attempts int, override *int) int {
	if override != nil {
		if *override < 0 {
			return 0
		}
		return *override
	}
	if attempts < 1 {
		return 0
	}
	seconds := 1
	for i := 1; i < attempts; i++ {
		seconds *= 2
		if seconds >= 60 {
			return 60
		}
	}
	return seconds
}
