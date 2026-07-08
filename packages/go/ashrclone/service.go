package ashrclone

import (
	"crypto/sha256"
	"encoding/hex"
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
	idem              map[string]idemRecord
	nextID            int
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
	run, ok := service.runs[runKey(tenantID, projectID, runID)]
	if !ok {
		return Envelope[RunUpload]{}, NotFoundError{Resource: "run"}
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
	if _, ok := service.runs[runKey(tenantID, projectID, runID)]; !ok {
		return Envelope[TraceBatch]{}, NotFoundError{Resource: "run"}
	}
	batchID := options.BatchID
	if batchID == "" {
		batchID = service.id("trace_batch", runID)
	}
	now := time.Now().UTC()
	batch := TraceBatch{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, BatchID: batchID, ObservationCount: len(observations), ObservationsSHA256: mustFingerprint(observations), RawPayloadIncluded: false, APIKeyID: options.APIKeyID, RequestID: options.RequestID, CreatedAt: now}
	service.traceBatches[traceBatchKey(tenantID, projectID, runID, batchID)] = batch
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
	if _, ok := service.runs[runKey(tenantID, projectID, runID)]; !ok {
		return Envelope[ArtifactManifest]{}, NotFoundError{Resource: "run"}
	}
	artifactID := options.ArtifactID
	if artifactID == "" {
		artifactID = service.id("artifact", runID)
	}
	now := time.Now().UTC()
	record := ArtifactManifest{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, RunID: runID, ArtifactID: artifactID, ManifestSHA256: mustFingerprint(manifest), RawPayloadIncluded: false, APIKeyID: options.APIKeyID, RequestID: options.RequestID, CreatedAt: now}
	service.artifactManifests[artifactManifestKey(tenantID, projectID, runID, artifactID)] = record
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
