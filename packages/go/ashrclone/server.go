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
	CreateAPIKey(tenantID, projectID string, options CreateAPIKeyOptions) (Envelope[APIKeyCreateResult], error)
	ListAPIKeys(tenantID, projectID string) (Envelope[APIKeyListResult], error)
	RevokeAPIKey(tenantID, projectID, keyID string) (Envelope[APIKeyRecord], error)
	VerifyAPIKeySecret(tenantID, projectID, keyID, secret, scope string) (Envelope[APIKeyVerifyResult], error)
	ConfigureAPIKeyRateLimit(tenantID, projectID, keyID, operation string, limit int) (Envelope[APIKeyRateLimit], error)
	APIKeyRateLimitSnapshot(tenantID, projectID, keyID string) (Envelope[APIKeyRateLimitSnapshot], error)
	PreflightAPIKey(options PreflightOptions) (Envelope[AuthPreflight], error)
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
	UsageSnapshot(tenantID, projectID string) (Envelope[UsageSnapshot], error)
	VerifyAuditChain(tenantID, projectID string) (Envelope[AuditChainVerification], error)
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

type requestAuthContext struct {
	TenantID string
	APIKeyID string
}

func resolveRequestAuth(writer http.ResponseWriter, request *http.Request, body JSONMap, requireKey bool, tenantCandidates ...string) (requestAuthContext, bool) {
	if stringValue(body, "api_key") != "" || strings.TrimSpace(request.Header.Get("Authorization")) != "" {
		writeError(writer, http.StatusBadRequest, "secret_input_rejected", "local Go control plane accepts api_key_id/auth_key_id handles only, not raw API key material")
		return requestAuthContext{}, false
	}
	headerTenant := firstNonEmpty(request.Header.Get("X-Ashr-Tenant-ID"), request.Header.Get("X-Ashr-Auth-Tenant-ID"))
	requestTenant := firstNonEmpty(tenantCandidates...)
	if headerTenant != "" && requestTenant != "" && headerTenant != requestTenant {
		writeError(writer, http.StatusForbidden, "tenant_mismatch", "tenant_id does not match authenticated tenant handle")
		return requestAuthContext{}, false
	}
	headerKeyID := firstNonEmpty(request.Header.Get("X-Ashr-API-Key-ID"), request.Header.Get("X-Ashr-Auth-Key-ID"))
	requestKeyID := firstNonEmpty(stringValue(body, "api_key_id"), stringValue(body, "auth_key_id"), request.URL.Query().Get("api_key_id"), request.URL.Query().Get("auth_key_id"))
	if headerKeyID != "" && requestKeyID != "" && headerKeyID != requestKeyID {
		writeError(writer, http.StatusForbidden, "api_key_mismatch", "api_key_id/auth_key_id does not match authenticated key handle")
		return requestAuthContext{}, false
	}
	auth := requestAuthContext{TenantID: firstNonEmpty(headerTenant, requestTenant), APIKeyID: firstNonEmpty(headerKeyID, requestKeyID)}
	if requireKey && auth.APIKeyID == "" {
		writeError(writer, http.StatusUnauthorized, "authentication_required", "api_key_id/auth_key_id handle is required for protected local Go control-plane routes")
		return requestAuthContext{}, false
	}
	return auth, true
}

func (server *HTTPServer) preflightRequest(writer http.ResponseWriter, auth requestAuthContext, projectID, scope, operation string) bool {
	_, err := server.service.PreflightAPIKey(PreflightOptions{TenantID: auth.TenantID, ProjectID: projectID, KeyID: auth.APIKeyID, Scope: scope, Operation: operation, Units: 1})
	if err != nil {
		writeServiceError(writer, err)
		return false
	}
	return true
}

func (server *HTTPServer) handleProject(writer http.ResponseWriter, request *http.Request, projectID string, parts []string) {
	if len(parts) >= 1 && parts[0] == "api-keys" {
		server.handleAPIKeys(writer, request, projectID, parts[1:])
		return
	}
	if request.Method == http.MethodGet && len(parts) == 1 && parts[0] == "worker-jobs" {
		server.handleListWorkerJobs(writer, request, projectID)
		return
	}
	if request.Method == http.MethodGet && len(parts) == 1 && parts[0] == "usage" {
		server.handleUsageSnapshot(writer, request, projectID)
		return
	}
	if (request.Method == http.MethodGet || request.Method == http.MethodPost) && len(parts) == 2 && parts[0] == "audit-chain" && parts[1] == "verify" {
		server.handleVerifyAuditChain(writer, request, projectID)
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
		auth, ok := resolveRequestAuth(writer, request, body, true, stringValue(body, "tenant_id"))
		if !ok {
			return
		}
		result, err := server.service.SubmitRun(auth.TenantID, projectID, stringValue(body, "dataset_id"), stringValue(body, "agent_ref"), stringValue(body, "run_id"), mapValue(body, "metadata"), IdempotencyOptions{Key: idempotencyKey(request, body), RequestID: requestID(request, body), APIKeyID: auth.APIKeyID})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) >= 1 && parts[0] == "worker-jobs" {
		auth, ok := resolveRequestAuth(writer, request, body, true, stringValue(body, "tenant_id"))
		if !ok {
			return
		}
		server.handleWorkerJobs(writer, request, auth.TenantID, projectID, parts[1:], body, auth)
		return
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) handleUsageSnapshot(writer http.ResponseWriter, request *http.Request, projectID string) {
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	auth, ok := resolveRequestAuth(writer, request, body, true, firstNonEmpty(request.URL.Query().Get("tenant_id"), stringValue(body, "tenant_id")))
	if !ok {
		return
	}
	if !server.preflightRequest(writer, auth, projectID, ScopeUsageRead, "usage") {
		return
	}
	result, err := server.service.UsageSnapshot(auth.TenantID, projectID)
	writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
}

func (server *HTTPServer) handleAPIKeys(writer http.ResponseWriter, request *http.Request, projectID string, parts []string) {
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	if _, ok := resolveRequestAuth(writer, request, body, false, firstNonEmpty(request.URL.Query().Get("tenant_id"), stringValue(body, "tenant_id"))); !ok {
		return
	}
	query := request.URL.Query()
	tenantID := firstNonEmpty(query.Get("tenant_id"), stringValue(body, "tenant_id"))
	if request.Method == http.MethodPost && len(parts) == 0 {
		result, err := server.service.CreateAPIKey(tenantID, projectID, CreateAPIKeyOptions{Name: stringValue(body, "name"), Scopes: stringSliceFromAny(body["scopes"]), KeyID: stringValue(body, "key_id"), AuthKeyID: stringValue(body, "auth_key_id"), RevealSecret: boolValue(body, "reveal_secret")})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodGet && len(parts) == 0 {
		result, err := server.service.ListAPIKeys(tenantID, projectID)
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodGet && len(parts) == 1 && parts[0] == "rate-limits" {
		keyID := firstNonEmpty(query.Get("key_id"), stringValue(body, "key_id"))
		result, err := server.service.APIKeyRateLimitSnapshot(tenantID, projectID, keyID)
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodPost && len(parts) == 1 && parts[0] == "preflight" {
		result, err := server.service.PreflightAPIKey(PreflightOptions{TenantID: tenantID, ProjectID: projectID, KeyID: firstNonEmpty(stringValue(body, "key_id"), stringValue(body, "api_key_id"), stringValue(body, "auth_key_id")), Scope: stringValue(body, "scope"), Operation: stringValue(body, "operation"), Units: intValue(body, "units")})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) == 2 && parts[1] == "revoke" && request.Method == http.MethodPost {
		result, err := server.service.RevokeAPIKey(tenantID, projectID, parts[0])
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) == 2 && parts[1] == "verify" && request.Method == http.MethodPost {
		result, err := server.service.VerifyAPIKeySecret(tenantID, projectID, parts[0], stringValue(body, "secret"), stringValue(body, "scope"))
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) == 2 && parts[1] == "rate-limit" && request.Method == http.MethodPost {
		result, err := server.service.ConfigureAPIKeyRateLimit(tenantID, projectID, parts[0], stringValue(body, "operation"), intValue(body, "limit"))
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) handleVerifyAuditChain(writer http.ResponseWriter, request *http.Request, projectID string) {
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	auth, ok := resolveRequestAuth(writer, request, body, true, firstNonEmpty(request.URL.Query().Get("tenant_id"), stringValue(body, "tenant_id")))
	if !ok {
		return
	}
	if !server.preflightRequest(writer, auth, projectID, ScopeAuditRead, "audit.chain.verify") {
		return
	}
	result, err := server.service.VerifyAuditChain(auth.TenantID, projectID)
	writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
}

func (server *HTTPServer) handleRunRoutes(writer http.ResponseWriter, request *http.Request, projectID, runID string, parts []string) {
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	auth, ok := resolveRequestAuth(writer, request, body, true, firstNonEmpty(request.URL.Query().Get("tenant_id"), stringValue(body, "tenant_id")))
	if !ok {
		return
	}
	tenantID := auth.TenantID
	if len(parts) == 1 {
		switch parts[0] {
		case "upload":
			if request.Method == http.MethodPost {
				result, err := server.service.UploadRun(tenantID, projectID, runID, mapValue(body, "result"), UploadRunOptions{UploadID: stringValue(body, "upload_id"), APIKeyID: auth.APIKeyID, IdempotencyKey: idempotencyKey(request, body), RequestID: requestID(request, body)})
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
		case "trace-events":
			if request.Method == http.MethodPost {
				result, err := server.service.IngestTrace(tenantID, projectID, runID, observationsFromAny(body["observations"]), IngestTraceOptions{BatchID: stringValue(body, "batch_id"), APIKeyID: auth.APIKeyID, IdempotencyKey: idempotencyKey(request, body), RequestID: requestID(request, body)})
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
		case "artifact-manifests":
			if request.Method == http.MethodPost {
				result, err := server.service.CreateArtifactManifest(tenantID, projectID, runID, mapValue(body, "manifest"), ArtifactManifestOptions{ArtifactID: stringValue(body, "artifact_id"), APIKeyID: auth.APIKeyID, IdempotencyKey: idempotencyKey(request, body), RequestID: requestID(request, body)})
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
			if request.Method == http.MethodGet {
				if !server.preflightRequest(writer, auth, projectID, ScopeArtifactManifestRead, "artifact_manifests") {
					return
				}
				result, err := server.service.ListArtifactManifests(tenantID, projectID, runID)
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
		}
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}
func (server *HTTPServer) handleWorkerJobs(writer http.ResponseWriter, request *http.Request, tenantID, projectID string, parts []string, body JSONMap, auth requestAuthContext) {
	if request.Method == http.MethodPost && len(parts) == 1 && parts[0] == "enqueue" {
		result, err := server.service.EnqueueWorkerJob(tenantID, projectID, stringValue(body, "job_type"), stringValue(body, "target_id"), mapValue(body, "payload"), EnqueueWorkerJobOptions{JobID: stringValue(body, "job_id"), Priority: intValue(body, "priority"), MaxAttempts: intValue(body, "max_attempts"), APIKeyID: auth.APIKeyID, IdempotencyKey: idempotencyKey(request, body), RequestID: requestID(request, body)})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodPost && len(parts) == 1 && parts[0] == "lease" {
		result, err := server.service.LeaseWorkerJob(tenantID, projectID, stringValue(body, "lease_owner_id"), LeaseWorkerJobOptions{LeaseSeconds: intValue(body, "lease_seconds"), JobType: stringValue(body, "job_type"), APIKeyID: auth.APIKeyID, RequestID: requestID(request, body)})
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
			result, err := server.service.CompleteWorkerJob(tenantID, projectID, jobID, stringValue(body, "lease_owner_id"), mapValue(body, "result"), CompleteWorkerJobOptions{APIKeyID: auth.APIKeyID, RequestID: requestID(request, body)})
			writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
			return
		case request.Method == http.MethodPost && action == "fail":
			result, err := server.service.FailWorkerJob(tenantID, projectID, jobID, stringValue(body, "lease_owner_id"), mapValue(body, "error"), FailWorkerJobOptions{RetryAfterSeconds: optionalInt(body, "retry_after_seconds"), APIKeyID: auth.APIKeyID, RequestID: requestID(request, body)})
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
	status := firstNonEmpty(query.Get("status"), stringValue(body, "status"))
	jobType := firstNonEmpty(query.Get("job_type"), stringValue(body, "job_type"))
	auth, ok := resolveRequestAuth(writer, request, body, true, firstNonEmpty(query.Get("tenant_id"), stringValue(body, "tenant_id")))
	if !ok {
		return
	}
	if !server.preflightRequest(writer, auth, projectID, ScopeWorkerJobList, "worker.job.list") {
		return
	}
	authKeyID := auth.APIKeyID
	limit, err := intFromQueryOrBody(query.Get("limit"), body, "limit")
	if err != nil {
		writeError(writer, http.StatusBadRequest, "validation_error", "limit must be an integer")
		return
	}
	result, err := server.service.ListWorkerJobs(auth.TenantID, projectID, ListWorkerJobsOptions{Status: status, JobType: jobType, Limit: limit, AuthKeyID: authKeyID})
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
	return JSONMap{"schema_version": ControlPlaneSchemaVersion, "routes": []string{"GET /health", "GET /healthz", "GET /v1/healthz", "GET /openapi.json", "GET /v1/openapi.json", "POST /bootstrap", "POST /v1/bootstrap", "POST /v1/projects/{project_id}/api-keys", "GET /v1/projects/{project_id}/api-keys", "POST /v1/projects/{project_id}/api-keys/preflight", "GET /v1/projects/{project_id}/api-keys/rate-limits", "POST /v1/projects/{project_id}/api-keys/{key_id}/verify", "POST /v1/projects/{project_id}/api-keys/{key_id}/revoke", "POST /v1/projects/{project_id}/api-keys/{key_id}/rate-limit", "POST /v1/projects/{project_id}/sdk-submit", "POST /v1/projects/{project_id}/runs/submit", "GET /v1/projects/{project_id}/usage", "GET /v1/projects/{project_id}/audit-chain/verify", "POST /v1/projects/{project_id}/audit-chain/verify", "POST /v1/projects/{project_id}/runs/{run_id}/upload", "POST /v1/projects/{project_id}/runs/{run_id}/trace-events", "POST /v1/projects/{project_id}/runs/{run_id}/artifact-manifests", "GET /v1/projects/{project_id}/runs/{run_id}/artifact-manifests", "POST /v1/projects/{project_id}/worker-jobs/enqueue", "POST /v1/projects/{project_id}/worker-jobs/lease", "GET /v1/projects/{project_id}/worker-jobs", "POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat", "POST /v1/projects/{project_id}/worker-jobs/{job_id}/complete", "POST /v1/projects/{project_id}/worker-jobs/{job_id}/fail"}, "go_owned": true, "backing_store": backingStore, "raw_payloads_included": false}
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
	var authz AuthzError
	var quota QuotaExceededError
	switch {
	case errors.As(err, &conflict):
		writeError(writer, http.StatusConflict, "idempotency_conflict", conflict.Error())
	case errors.As(err, &notFound):
		writeError(writer, http.StatusNotFound, "not_found", notFound.Error())
	case errors.As(err, &authz):
		code := authz.Code
		if code == "" {
			code = "forbidden"
		}
		writeError(writer, http.StatusForbidden, code, authz.Error())
	case errors.As(err, &quota):
		writeError(writer, http.StatusTooManyRequests, "quota_exceeded", quota.Error())
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

func boolValue(body JSONMap, key string) bool {
	value, ok := body[key].(bool)
	return ok && value
}

func stringSliceFromAny(value any) []string {
	switch typed := value.(type) {
	case []string:
		return append([]string(nil), typed...)
	case []any:
		output := make([]string, 0, len(typed))
		for _, item := range typed {
			if text, ok := item.(string); ok && strings.TrimSpace(text) != "" {
				output = append(output, text)
			}
		}
		return output
	default:
		return nil
	}
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
