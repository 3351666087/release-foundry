package ashrclone

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
)

type HTTPServer struct {
	service      ControlPlaneBackend
	backendName  string
	backendReady bool
}

type ControlPlaneBackend interface {
	BootstrapProject(tenantName, projectName string, dataset Dataset, tenantID, projectID string) (Envelope[BootstrapResult], error)
	SubmitRun(tenantID, projectID, datasetID, agentRef, runID string, metadata JSONMap, options IdempotencyOptions) (Envelope[Run], error)
	EnqueueWorkerJob(tenantID, projectID, jobType, targetID string, payload JSONMap, options EnqueueWorkerJobOptions) (Envelope[WorkerJob], error)
	LeaseWorkerJob(tenantID, projectID, leaseOwnerID string, options LeaseWorkerJobOptions) (Envelope[WorkerLeaseResult], error)
	HeartbeatWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, leaseSeconds int) (Envelope[WorkerJob], error)
	CompleteWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, result JSONMap, options CompleteWorkerJobOptions) (Envelope[WorkerJob], error)
	FailWorkerJob(tenantID, projectID, jobID, leaseOwnerID string, failure JSONMap, options FailWorkerJobOptions) (Envelope[WorkerJob], error)
	ListWorkerJobs(tenantID, projectID string, options ListWorkerJobsOptions) (Envelope[WorkerJobList], error)
	UploadRun(tenantID, projectID, runID string, result JSONMap, options UploadRunOptions) (Envelope[RunUpload], error)
	IngestTrace(tenantID, projectID, runID string, observations []JSONMap, options IngestTraceOptions) (Envelope[TraceBatch], error)
	CreateArtifactManifest(tenantID, projectID, runID string, manifest JSONMap, options ArtifactManifestOptions) (Envelope[ArtifactManifest], error)
	ListArtifactManifests(tenantID, projectID, runID string) (Envelope[ArtifactManifestList], error)
}

type HTTPServerOptions struct {
	BackendName  string
	BackendReady bool
}

func NewHTTPServer(service ControlPlaneBackend) http.Handler {
	return NewHTTPServerWithOptions(service, HTTPServerOptions{BackendName: "memory_service_v0", BackendReady: true})
}

func NewHTTPServerWithOptions(service ControlPlaneBackend, options HTTPServerOptions) http.Handler {
	if service == nil {
		service = NewMemoryService()
	}
	backendName := strings.TrimSpace(options.BackendName)
	if backendName == "" {
		backendName = "memory_service_v0"
	}
	return &HTTPServer{service: service, backendName: backendName, backendReady: options.BackendReady}
}

func NewHTTPHandler(service ControlPlaneBackend) http.Handler {
	return NewHTTPServer(service)
}

func (server *HTTPServer) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	writer.Header().Set("Content-Type", "application/json")
	if request.Method == http.MethodGet && (request.URL.Path == "/health" || request.URL.Path == "/healthz" || request.URL.Path == "/v1/healthz") {
		writeJSON(writer, http.StatusOK, JSONMap{"schema_version": ControlPlaneSchemaVersion, "status": "ok", "service": "ashr-go-control-plane", "backend": server.backendName, "backend_ready": server.backendReady, "backend_mode": backendMode(server.backendName), "local_only": server.backendName == "memory_service_v0", "ashr_api_used": false})
		return
	}
	if request.Method == http.MethodGet && (request.URL.Path == "/openapi.json" || request.URL.Path == "/v1/openapi.json") {
		writeJSON(writer, http.StatusOK, GoRouteManifest(server.backendName))
		return
	}
	if request.URL.Path == "/bootstrap" || request.URL.Path == "/v1/bootstrap" {
		server.handleBootstrap(writer, request)
		return
	}
	parts := pathParts(request.URL.Path)
	if len(parts) >= 3 && parts[0] == "v1" && parts[1] == "projects" {
		server.handleProject(writer, request, parts[2], parts[3:])
		return
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) handleBootstrap(writer http.ResponseWriter, request *http.Request) {
	if request.Method != http.MethodPost {
		writeError(writer, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
		return
	}
	body, ok := readJSONBody(writer, request)
	if !ok {
		return
	}
	result, err := server.service.BootstrapProject(stringValue(body, "tenant_name"), stringValue(body, "project_name"), datasetFromRequest(body), stringValue(body, "tenant_id"), stringValue(body, "project_id"))
	writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
}

func (server *HTTPServer) handleProject(writer http.ResponseWriter, request *http.Request, projectID string, parts []string) {
	if request.Method == http.MethodGet && len(parts) == 1 && parts[0] == "worker-jobs" {
		server.handleListWorkerJobs(writer, request, projectID)
		return
	}
	if len(parts) >= 3 && parts[0] == "runs" {
		server.handleRunRoutes(writer, request, projectID, parts[1], parts[2:])
		return
	}
	body, ok := readJSONBody(writer, request)
	if !ok {
		return
	}
	if request.Method == http.MethodPost && ((len(parts) == 1 && parts[0] == "sdk-submit") || (len(parts) == 2 && parts[0] == "runs" && parts[1] == "submit")) {
		result, err := server.service.SubmitRun(stringValue(body, "tenant_id"), projectID, stringValue(body, "dataset_id"), stringValue(body, "agent_ref"), stringValue(body, "run_id"), mapValue(body, "metadata"), IdempotencyOptions{Key: idempotencyKey(request, body), RequestID: requestID(request, body), APIKeyID: stringValue(body, "api_key_id")})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) >= 1 && parts[0] == "worker-jobs" {
		server.handleWorkerJobs(writer, request, stringValue(body, "tenant_id"), projectID, parts[1:], body)
		return
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) handleRunRoutes(writer http.ResponseWriter, request *http.Request, projectID, runID string, parts []string) {
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	tenantID := firstNonEmpty(request.URL.Query().Get("tenant_id"), stringValue(body, "tenant_id"))
	if len(parts) == 1 {
		switch parts[0] {
		case "upload":
			if request.Method == http.MethodPost {
				result, err := server.service.UploadRun(tenantID, projectID, runID, mapValue(body, "result"), UploadRunOptions{UploadID: stringValue(body, "upload_id"), APIKeyID: stringValue(body, "api_key_id"), IdempotencyKey: idempotencyKey(request, body), RequestID: requestID(request, body)})
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
		case "trace-events":
			if request.Method == http.MethodPost {
				result, err := server.service.IngestTrace(tenantID, projectID, runID, observationsFromAny(body["observations"]), IngestTraceOptions{BatchID: stringValue(body, "batch_id"), APIKeyID: stringValue(body, "api_key_id"), IdempotencyKey: idempotencyKey(request, body), RequestID: requestID(request, body)})
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
		case "artifact-manifests":
			if request.Method == http.MethodPost {
				result, err := server.service.CreateArtifactManifest(tenantID, projectID, runID, mapValue(body, "manifest"), ArtifactManifestOptions{ArtifactID: stringValue(body, "artifact_id"), APIKeyID: stringValue(body, "api_key_id"), IdempotencyKey: idempotencyKey(request, body), RequestID: requestID(request, body)})
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
			if request.Method == http.MethodGet {
				result, err := server.service.ListArtifactManifests(tenantID, projectID, runID)
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
		}
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) handleWorkerJobs(writer http.ResponseWriter, request *http.Request, tenantID, projectID string, parts []string, body JSONMap) {
	if request.Method == http.MethodPost && len(parts) == 1 && parts[0] == "enqueue" {
		result, err := server.service.EnqueueWorkerJob(tenantID, projectID, stringValue(body, "job_type"), stringValue(body, "target_id"), mapValue(body, "payload"), EnqueueWorkerJobOptions{JobID: stringValue(body, "job_id"), Priority: intValue(body, "priority"), MaxAttempts: intValue(body, "max_attempts"), APIKeyID: stringValue(body, "api_key_id"), IdempotencyKey: idempotencyKey(request, body), RequestID: requestID(request, body)})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodPost && len(parts) == 1 && parts[0] == "lease" {
		result, err := server.service.LeaseWorkerJob(tenantID, projectID, stringValue(body, "lease_owner_id"), LeaseWorkerJobOptions{LeaseSeconds: intValue(body, "lease_seconds"), JobType: stringValue(body, "job_type"), APIKeyID: stringValue(body, "api_key_id"), RequestID: requestID(request, body)})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) == 2 {
		jobID, action := parts[0], parts[1]
		switch {
		case request.Method == http.MethodPost && action == "heartbeat":
			result, err := server.service.HeartbeatWorkerJob(tenantID, projectID, jobID, stringValue(body, "lease_owner_id"), intValue(body, "lease_seconds"))
			writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
			return
		case request.Method == http.MethodPost && action == "complete":
			result, err := server.service.CompleteWorkerJob(tenantID, projectID, jobID, stringValue(body, "lease_owner_id"), mapValue(body, "result"), CompleteWorkerJobOptions{APIKeyID: stringValue(body, "api_key_id"), RequestID: requestID(request, body)})
			writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
			return
		case request.Method == http.MethodPost && action == "fail":
			result, err := server.service.FailWorkerJob(tenantID, projectID, jobID, stringValue(body, "lease_owner_id"), mapValue(body, "error"), FailWorkerJobOptions{RetryAfterSeconds: optionalInt(body, "retry_after_seconds"), APIKeyID: stringValue(body, "api_key_id"), RequestID: requestID(request, body)})
			writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
			return
		}
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) handleListWorkerJobs(writer http.ResponseWriter, request *http.Request, projectID string) {
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	query := request.URL.Query()
	tenantID := firstNonEmpty(query.Get("tenant_id"), stringValue(body, "tenant_id"))
	status := firstNonEmpty(query.Get("status"), stringValue(body, "status"))
	jobType := firstNonEmpty(query.Get("job_type"), stringValue(body, "job_type"))
	authKeyID := firstNonEmpty(query.Get("auth_key_id"), stringValue(body, "auth_key_id"))
	limit, err := intFromQueryOrBody(query.Get("limit"), body, "limit")
	if err != nil {
		writeError(writer, http.StatusBadRequest, "validation_error", "limit must be an integer")
		return
	}
	result, err := server.service.ListWorkerJobs(tenantID, projectID, ListWorkerJobsOptions{Status: status, JobType: jobType, Limit: limit, AuthKeyID: authKeyID})
	writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
}

func backendMode(backendName string) string {
	if backendName == "memory_service_v0" {
		return "local_memory"
	}
	return "postgres"
}

func GoRouteManifest(backendName ...string) JSONMap {
	backingStore := "memory_service_v0"
	if len(backendName) > 0 && strings.TrimSpace(backendName[0]) != "" {
		backingStore = strings.TrimSpace(backendName[0])
	}
	return JSONMap{"schema_version": ControlPlaneSchemaVersion, "routes": []string{"GET /health", "GET /healthz", "GET /v1/healthz", "GET /openapi.json", "GET /v1/openapi.json", "POST /bootstrap", "POST /v1/bootstrap", "POST /v1/projects/{project_id}/sdk-submit", "POST /v1/projects/{project_id}/runs/submit", "POST /v1/projects/{project_id}/runs/{run_id}/upload", "POST /v1/projects/{project_id}/runs/{run_id}/trace-events", "POST /v1/projects/{project_id}/runs/{run_id}/artifact-manifests", "GET /v1/projects/{project_id}/runs/{run_id}/artifact-manifests", "POST /v1/projects/{project_id}/worker-jobs/enqueue", "POST /v1/projects/{project_id}/worker-jobs/lease", "GET /v1/projects/{project_id}/worker-jobs", "POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat", "POST /v1/projects/{project_id}/worker-jobs/{job_id}/complete", "POST /v1/projects/{project_id}/worker-jobs/{job_id}/fail"}, "go_owned": true, "backing_store": backingStore, "raw_payloads_included": false}
}
func readJSONBody(writer http.ResponseWriter, request *http.Request) (JSONMap, bool) {
	if request.Method == http.MethodGet || request.Body == nil {
		return JSONMap{}, true
	}
	return decodeJSONBody(writer, request)
}

func readJSONBodyAllowGET(writer http.ResponseWriter, request *http.Request) (JSONMap, bool) {
	if request.Body == nil || request.Body == http.NoBody {
		return JSONMap{}, true
	}
	return decodeJSONBody(writer, request)
}

func decodeJSONBody(writer http.ResponseWriter, request *http.Request) (JSONMap, bool) {
	defer request.Body.Close()
	body := JSONMap{}
	decoder := json.NewDecoder(request.Body)
	decoder.UseNumber()
	if err := decoder.Decode(&body); err != nil {
		writeError(writer, http.StatusBadRequest, "invalid_json", "request body must be a JSON object")
		return nil, false
	}
	return body, true
}

func writeEnvelopeResult[T any](writer http.ResponseWriter, status int, result T, err error) {
	if err != nil {
		writeServiceError(writer, err)
		return
	}
	writeJSON(writer, status, result)
}

func writeServiceError(writer http.ResponseWriter, err error) {
	var conflict IdempotencyConflictError
	var notFound NotFoundError
	switch {
	case errors.As(err, &conflict):
		writeError(writer, http.StatusConflict, "idempotency_conflict", conflict.Error())
	case errors.As(err, &notFound):
		writeError(writer, http.StatusNotFound, "not_found", notFound.Error())
	default:
		writeError(writer, http.StatusBadRequest, "validation_error", err.Error())
	}
}

func writeError(writer http.ResponseWriter, status int, code, message string) {
	writeJSON(writer, status, JSONMap{"schema_version": ControlPlaneSchemaVersion, "status": "error", "error": JSONMap{"code": code, "message": RedactSensitive(message)}})
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(RedactSensitive(value))
}

func pathParts(path string) []string {
	trimmed := strings.Trim(path, "/")
	if trimmed == "" {
		return nil
	}
	parts := strings.Split(trimmed, "/")
	for index, part := range parts {
		parts[index] = strings.TrimSpace(part)
	}
	return parts
}

func observationsFromAny(value any) []JSONMap {
	items, ok := value.([]any)
	if !ok {
		return nil
	}
	observations := make([]JSONMap, 0, len(items))
	for _, item := range items {
		observations = append(observations, jsonMapFromAny(item))
	}
	return observations
}
func datasetFromRequest(body JSONMap) Dataset {
	dataset := datasetFromJSON(body["dataset"])
	if dataset.DatasetID == "" {
		dataset.DatasetID = stringValue(body, "dataset_id")
	}
	if dataset.Name == "" {
		dataset.Name = stringValue(body, "dataset_name")
	}
	if dataset.Cases == nil {
		dataset.Cases = datasetCasesFromAny(body["cases"])
	}
	return dataset
}

func datasetFromJSON(value any) Dataset {
	mapped, ok := value.(map[string]any)
	if !ok {
		if jsonMap, ok := value.(JSONMap); ok {
			mapped = jsonMap
		} else {
			return Dataset{}
		}
	}
	return Dataset{DatasetID: stringFromAny(mapped["dataset_id"]), Name: stringFromAny(mapped["name"]), Cases: datasetCasesFromAny(mapped["cases"]), Metadata: jsonMapFromAny(mapped["metadata"])}
}

func datasetCasesFromAny(value any) []DatasetCase {
	if value == nil {
		return nil
	}
	payload, err := json.Marshal(value)
	if err != nil {
		return nil
	}
	var cases []DatasetCase
	if err := json.Unmarshal(payload, &cases); err != nil {
		return nil
	}
	return cases
}

func idempotencyKey(request *http.Request, body JSONMap) string {
	if header := request.Header.Get("Idempotency-Key"); header != "" {
		return header
	}
	return stringValue(body, "idempotency_key")
}

func requestID(request *http.Request, body JSONMap) string {
	if header := request.Header.Get("X-Request-ID"); header != "" {
		return header
	}
	return stringValue(body, "request_id")
}

func stringValue(body JSONMap, key string) string { return stringFromAny(body[key]) }

func stringFromAny(value any) string {
	if typed, ok := value.(string); ok {
		return typed
	}
	return ""
}

func mapValue(body JSONMap, key string) JSONMap { return jsonMapFromAny(body[key]) }

func jsonMapFromAny(value any) JSONMap {
	switch typed := value.(type) {
	case JSONMap:
		return cloneMap(typed)
	case map[string]any:
		return cloneMap(JSONMap(typed))
	default:
		return JSONMap{}
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

func intFromQueryOrBody(raw string, body JSONMap, key string) (int, error) {
	if raw != "" {
		return strconv.Atoi(raw)
	}
	return intValue(body, key), nil
}

func intValue(body JSONMap, key string) int {
	value, ok := intFromAny(body[key])
	if !ok {
		return 0
	}
	return value
}

func optionalInt(body JSONMap, key string) *int {
	value, ok := intFromAny(body[key])
	if !ok {
		return nil
	}
	return &value
}

func intFromAny(value any) (int, bool) {
	switch typed := value.(type) {
	case int:
		return typed, true
	case int64:
		return int(typed), true
	case float64:
		return int(typed), true
	case json.Number:
		parsed, err := typed.Int64()
		return int(parsed), err == nil
	default:
		return 0, false
	}
}
