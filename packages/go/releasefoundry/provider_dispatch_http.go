package releasefoundry

import (
	"database/sql"
	"errors"
	"net/http"
	"strings"
	"time"
)

type ProviderDispatchBackend interface {
	SubmitProviderDispatch(string, string, string, string, JSONMap, SubmitProviderDispatchOptions) (Envelope[ProviderDispatch], error)
	ClaimProviderDispatch(string, string, string, ClaimProviderDispatchOptions) (Envelope[ProviderDispatchClaim], error)
	ClaimProviderDispatchReconciliation(string, string, string, ReconcileProviderDispatchOptions) (Envelope[ProviderDispatchClaim], error)
	GetProviderDispatch(string, string, string) (Envelope[ProviderDispatch], error)
	HeartbeatProviderDispatch(string, string, string, string, int64, int) (Envelope[ProviderDispatch], error)
	ObserveProviderDispatchStream(string, string, string, string, int64, ObserveProviderDispatchStreamOptions) (Envelope[ProviderDispatch], error)
	CompleteProviderDispatch(string, string, string, string, int64, CompleteProviderDispatchOptions) (Envelope[ProviderDispatch], error)
	MarkProviderDispatchIndeterminate(string, string, string, string, int64, string, JSONMap, time.Time) (Envelope[ProviderDispatch], error)
}

func (server *HTTPServer) handleProviderDispatch(writer http.ResponseWriter, request *http.Request, tenantID, projectID string, parts []string) {
	if server.providerDispatch == nil {
		writeError(writer, http.StatusServiceUnavailable, "provider_dispatch_unavailable", "provider dispatch backend is unavailable")
		return
	}
	body, ok := readJSONBody(writer, request)
	if !ok {
		return
	}
	auth, ok := resolveRequestAuth(writer, request, body, true, tenantID)
	if !ok {
		return
	}
	scope, operation, ok := providerDispatchAuthorization(request.Method, parts)
	if !ok {
		writeError(writer, http.StatusNotFound, "not_found", "provider dispatch route not found")
		return
	}
	if !server.preflightRequest(writer, auth, projectID, scope, operation) {
		return
	}
	if request.Method == http.MethodPost && len(parts) == 0 {
		result, err := server.providerDispatch.SubmitProviderDispatch(
			tenantID, projectID, stringValue(body, "provider"), stringValue(body, "operation"),
			jsonMapValue(body, "request"), SubmitProviderDispatchOptions{DispatchID: stringValue(body, "dispatch_id")})
		writeProviderDispatchResult(writer, http.StatusCreated, result.Result, err)
		return
	}
	if request.Method == http.MethodPost && len(parts) == 1 && parts[0] == "claim" {
		result, err := server.providerDispatch.ClaimProviderDispatch(
			tenantID, projectID, stringValue(body, "lease_owner_id"),
			ClaimProviderDispatchOptions{Provider: stringValue(body, "provider"), Operation: stringValue(body, "operation"), LeaseSeconds: intValue(body, "lease_seconds")})
		writeProviderDispatchResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodPost && len(parts) == 2 && parts[0] == "reconciliation" && parts[1] == "claim" {
		result, err := server.providerDispatch.ClaimProviderDispatchReconciliation(
			tenantID, projectID, stringValue(body, "lease_owner_id"),
			ReconcileProviderDispatchOptions{LeaseSeconds: intValue(body, "lease_seconds")})
		writeProviderDispatchResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) < 1 || strings.TrimSpace(parts[0]) == "" {
		writeError(writer, http.StatusNotFound, "not_found", "provider dispatch route not found")
		return
	}
	dispatchID := parts[0]
	if request.Method == http.MethodGet && len(parts) == 1 {
		result, err := server.providerDispatch.GetProviderDispatch(tenantID, projectID, dispatchID)
		writeProviderDispatchResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method != http.MethodPost || len(parts) != 2 {
		writeError(writer, http.StatusNotFound, "not_found", "provider dispatch route not found")
		return
	}
	owner, fence := stringValue(body, "lease_owner_id"), int64(intValue(body, "fencing_token"))
	var result Envelope[ProviderDispatch]
	var err error
	switch parts[1] {
	case "heartbeat":
		result, err = server.providerDispatch.HeartbeatProviderDispatch(tenantID, projectID, dispatchID, owner, fence, intValue(body, "lease_seconds"))
	case "observe-stream":
		result, err = server.providerDispatch.ObserveProviderDispatchStream(tenantID, projectID, dispatchID, owner, fence, ObserveProviderDispatchStreamOptions{Stream: jsonMapValue(body, "stream")})
	case "complete":
		result, err = server.providerDispatch.CompleteProviderDispatch(tenantID, projectID, dispatchID, owner, fence, CompleteProviderDispatchOptions{
			ProviderRequestID: stringValue(body, "provider_request_id"), Proof: jsonMapValue(body, "proof"), Response: jsonMapValue(body, "response")})
	case "indeterminate":
		result, err = server.providerDispatch.MarkProviderDispatchIndeterminate(
			tenantID, projectID, dispatchID, owner, fence, stringValue(body, "reason"),
			jsonMapValue(body, "failure"), timeValue(body, "next_reconcile_at"))
	default:
		writeError(writer, http.StatusNotFound, "not_found", "provider dispatch route not found")
		return
	}
	writeProviderDispatchResult(writer, http.StatusOK, result.Result, err)
}

func providerDispatchAuthorization(method string, parts []string) (string, string, bool) {
	if method == http.MethodPost && len(parts) == 0 {
		return ScopeRunSubmit, "provider_dispatch.submit", true
	}
	if method == http.MethodPost && len(parts) == 1 && parts[0] == "claim" {
		return ScopeWorkerJobLease, "provider_dispatch.claim", true
	}
	if method == http.MethodPost && len(parts) == 2 && parts[0] == "reconciliation" && parts[1] == "claim" {
		return ScopeWorkerJobLease, "provider_dispatch.reconciliation.claim", true
	}
	if method == http.MethodGet && len(parts) == 1 && strings.TrimSpace(parts[0]) != "" {
		return ScopeRunLifecycleRead, "provider_dispatch.get", true
	}
	if method != http.MethodPost || len(parts) != 2 || strings.TrimSpace(parts[0]) == "" {
		return "", "", false
	}
	switch parts[1] {
	case "heartbeat":
		return ScopeWorkerJobLease, "provider_dispatch.heartbeat", true
	case "observe-stream":
		return ScopeTraceIngest, "provider_dispatch.observe_stream", true
	case "complete":
		return ScopeWorkerJobComplete, "provider_dispatch.complete", true
	case "indeterminate":
		return ScopeWorkerJobFail, "provider_dispatch.indeterminate", true
	default:
		return "", "", false
	}
}

func writeProviderDispatchResult[T any](writer http.ResponseWriter, status int, result T, err error) {
	if err == nil {
		writeJSON(writer, status, result)
		return
	}
	switch {
	case errors.Is(err, sql.ErrNoRows):
		writeError(writer, http.StatusNotFound, "provider_dispatch_not_found", "provider dispatch was not found")
	case errors.Is(err, ErrProviderDispatchConflict):
		writeError(writer, http.StatusConflict, "provider_dispatch_conflict", "provider dispatch conflicts with durable state")
	case errors.Is(err, ErrProviderDispatchFence):
		writeError(writer, http.StatusConflict, "provider_dispatch_fence", "provider dispatch lease or fencing token was rejected")
	case errors.Is(err, ErrProviderDispatchCancelled):
		writeError(writer, http.StatusRequestTimeout, "provider_dispatch_cancelled", "provider dispatch operation was cancelled")
	case errors.Is(err, ErrProviderDispatchDeadline):
		writeError(writer, http.StatusGatewayTimeout, "provider_dispatch_deadline", "provider dispatch operation exceeded its deadline")
	case errors.Is(err, ErrProviderDispatchContention):
		writeError(writer, http.StatusConflict, "provider_dispatch_contention", "provider dispatch is temporarily contended")
	case errors.Is(err, ErrProviderDispatchIndeterminate):
		writeError(writer, http.StatusServiceUnavailable, "provider_dispatch_indeterminate", "provider dispatch commit outcome is indeterminate")
	default:
		writeError(writer, http.StatusServiceUnavailable, "provider_dispatch_unavailable", "provider dispatch backend is unavailable")
	}
}

func jsonMapValue(body JSONMap, key string) JSONMap {
	value, _ := body[key].(map[string]any)
	return cloneMap(value)
}

func timeValue(body JSONMap, key string) time.Time {
	raw := stringValue(body, key)
	parsed, _ := time.Parse(time.RFC3339Nano, raw)
	return parsed
}
