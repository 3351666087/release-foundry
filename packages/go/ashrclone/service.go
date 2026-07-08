package ashrclone

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"sync"
)

type MemoryService struct {
	mu       sync.Mutex
	tenants  map[string]Tenant
	projects map[string]Project
	datasets map[string]Dataset
	runs     map[string]Run
	idem     map[string]idemRecord
	nextID   int
}

func NewMemoryService() *MemoryService {
	return &MemoryService{
		tenants:  map[string]Tenant{},
		projects: map[string]Project{},
		datasets: map[string]Dataset{},
		runs:     map[string]Run{},
		idem:     map[string]idemRecord{},
		nextID:   1,
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
