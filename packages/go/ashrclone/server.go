package ashrclone

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"
)

type HTTPServer struct {
	service                            ControlPlaneBackend
	paymentReconciliation              *PaymentReconciliationService
	paymentDomain                      *PaymentDomainService
	unifiedIdentity                    *UnifiedIdentityService
	unifiedIdentityStore               UnifiedIdentityHTTPStore
	identityLifecycle                  *IdentityLifecycleService
	identitySessions                   IdentityHTTPSessionResolver
	identitySecurityTickets            IdentitySecurityTicketResolver
	identitySecurity                   IdentitySecurityHTTPStore
	identityVerification               *IdentityVerificationService
	identityVerificationResponsePolicy *IdentityVerificationResponsePolicy
	identitySessionReceiptTransport    IdentitySessionReceiptTransport
	oauthProviders                     map[string]*OAuthService
	githubOAuth                        *GitHubOAuthService
	providerDispatch                   ProviderDispatchBackend
	identity                           *IdentityService
	identityDelivery                   IdentityChallengeDeliverer
	identityRateLimiter                IdentityRateLimiter
	identityAudit                      IdentityAuditSink
	oauth                              *OAuthFlowCoordinator
	backendName                        string
	backendReady                       bool
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
	RunLifecycle(tenantID, projectID, runID string) (Envelope[RunLifecycle], error)
	ConfigureUsageQuota(tenantID, projectID, operation string, limit int) (Envelope[UsageOperationTotal], error)
	UsageSnapshot(tenantID, projectID string) (Envelope[UsageSnapshot], error)
	CreateBillingCheckoutPlan(tenantID, projectID string, request BillingPlanRequest, options IdempotencyOptions) (Envelope[BillingCheckoutPlan], error)
	CreateBillingPortalPlan(tenantID, projectID string, request BillingPlanRequest, options IdempotencyOptions) (Envelope[BillingPortalPlan], error)
	IngestBillingWebhook(tenantID, projectID string, event BillingWebhookIngest, options IdempotencyOptions) (Envelope[BillingWebhookIngest], error)
	BillingLedger(tenantID, projectID string) (Envelope[BillingLedger], error)
	AuditLog(tenantID, projectID string, options AuditLogOptions) (Envelope[AuditEventList], error)
	VerifyAuditChain(tenantID, projectID string) (Envelope[AuditChainVerification], error)
	BuildReleaseEvidencePacket(tenantID, projectID, runID string) (Envelope[ReleaseEvidencePacket], error)
	VerifyReleaseEvidencePacket(tenantID, projectID, runID string, packet JSONMap) (Envelope[ReleaseEvidenceVerification], error)
}

type HTTPServerOptions struct {
	BackendName                        string
	BackendReady                       bool
	PaymentReconciliation              *PaymentReconciliationService
	PaymentDomain                      *PaymentDomainService
	UnifiedIdentity                    *UnifiedIdentityService
	UnifiedIdentityStore               UnifiedIdentityHTTPStore
	IdentityLifecycle                  *IdentityLifecycleService
	IdentitySessions                   IdentityHTTPSessionResolver
	IdentitySecurityTickets            IdentitySecurityTicketResolver
	IdentitySecurity                   IdentitySecurityHTTPStore
	IdentityVerification               *IdentityVerificationService
	IdentityVerificationResponsePolicy *IdentityVerificationResponsePolicy
	IdentitySessionReceiptTransport    IdentitySessionReceiptTransport
	OAuthProviders                     map[string]*OAuthService
	GitHubOAuth                        *GitHubOAuthService
	ProviderDispatch                   ProviderDispatchBackend
	IdentityService                    *IdentityService
	IdentityDelivery                   IdentityChallengeDeliverer
	IdentityRateLimiter                IdentityRateLimiter
	IdentityAudit                      IdentityAuditSink
	OAuthCoordinator                   *OAuthFlowCoordinator
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
	oauthProviders := make(map[string]*OAuthService, len(options.OAuthProviders))
	for providerName, oauthService := range options.OAuthProviders {
		normalizedProvider := strings.ToLower(strings.TrimSpace(providerName))
		if normalizedProvider == "" || oauthService == nil || oauthService.ProviderName() != normalizedProvider {
			continue
		}
		oauthProviders[normalizedProvider] = oauthService
	}
	identity := options.IdentityService
	oauth := options.OAuthCoordinator
	if identity == nil && oauth != nil {
		identity = oauth.identity
	}
	if identity == nil {
		identity = NewIdentityService()
	}
	// OAuth validation and canonical-account mutation must share one identity
	// authority. A mismatched coordinator is disabled rather than allowing
	// tickets or sessions to cross service instances.
	if oauth != nil && oauth.identity != identity {
		oauth = nil
	}
	delivery := options.IdentityDelivery
	if delivery == nil {
		delivery = unavailableIdentityDeliverer{}
	}
	rateLimiter := options.IdentityRateLimiter
	if rateLimiter == nil {
		rateLimiter = allowIdentityRateLimiter{}
	}
	audit := options.IdentityAudit
	if audit == nil {
		audit = discardIdentityAuditSink{}
	}
	return &HTTPServer{
		service:                            service,
		paymentReconciliation:              options.PaymentReconciliation,
		paymentDomain:                      options.PaymentDomain,
		unifiedIdentity:                    options.UnifiedIdentity,
		unifiedIdentityStore:               options.UnifiedIdentityStore,
		identityLifecycle:                  options.IdentityLifecycle,
		identitySessions:                   options.IdentitySessions,
		identitySecurityTickets:            options.IdentitySecurityTickets,
		identitySecurity:                   options.IdentitySecurity,
		identityVerification:               options.IdentityVerification,
		identityVerificationResponsePolicy: options.IdentityVerificationResponsePolicy,
		identitySessionReceiptTransport:    options.IdentitySessionReceiptTransport,
		oauthProviders:                     oauthProviders,
		githubOAuth:                        options.GitHubOAuth,
		providerDispatch:                   options.ProviderDispatch,
		identity:                           identity,
		identityDelivery:                   delivery,
		identityRateLimiter:                rateLimiter,
		identityAudit:                      audit,
		oauth:                              oauth,
		backendName:                        backendName,
		backendReady:                       options.BackendReady,
	}
}

func NewHTTPHandler(service ControlPlaneBackend) http.Handler {
	return NewHTTPServer(service)
}

func (server *HTTPServer) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	writer.Header().Set("Content-Type", "application/json")
	if request.Method == http.MethodGet && (request.URL.Path == "/health" || request.URL.Path == "/healthz" || request.URL.Path == "/v1/healthz") {
		writeJSON(writer, http.StatusOK, JSONMap{"schema_version": ControlPlaneSchemaVersion, "status": "ok", "service": "ashr-go-control-plane", "backend": server.backendName, "ready": server.backendReady, "backend_ready": server.backendReady, "backend_mode": backendMode(server.backendName), "local_only": server.backendName == "memory_service_v0", "ashr_api_used": false})
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
	callbackParts := pathParts(request.URL.Path)
	if len(callbackParts) == 3 && callbackParts[0] == "oauth" && callbackParts[2] == "callback" {
		if callbackParts[1] == "github" && server.githubOAuth != nil {
			server.handleGitHubOAuthCallback(writer, request)
			return
		}
		if _, configured := server.oauthProviders[callbackParts[1]]; configured {
			server.handleOAuthCallback(writer, request, callbackParts[1])
			return
		}
	}
	parts := pathParts(request.URL.Path)
	if server.handleIdentityRoute(writer, request, parts) {
		return
	}
	if len(parts) >= 2 && parts[0] == "v1" && parts[1] == "identity" {
		server.handleIdentityLifecycle(writer, request, parts[2:])
		return
	}
	if len(parts) == 3 && parts[0] == "v1" && parts[1] == "identity-verification" {
		server.handleIdentityVerification(writer, request, parts[2])
		return
	}
	if len(parts) >= 3 && parts[0] == "v1" && parts[1] == "accounts" {
		server.handleUnifiedIdentityAccount(writer, request, parts[2], parts[3:])
		return
	}
	if len(parts) >= 6 && parts[0] == "v1" && parts[1] == "tenants" &&
		parts[3] == "projects" && parts[5] == "provider-dispatches" {
		server.handleProviderDispatch(writer, request, parts[2], parts[4], parts[6:])
		return
	}
	if len(parts) == 7 && parts[0] == "v1" && parts[1] == "projects" &&
		parts[3] == "accounts" && parts[5] == "browser-sessions" && parts[6] == "refresh" {
		server.handleIdentitySessionRefresh(writer, request, parts[2], parts[4])
		return
	}
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
	TenantID     string
	APIKeyID     string
	BearerSecret string
}

func resolveRequestAuth(writer http.ResponseWriter, request *http.Request, body JSONMap, requireKey bool, tenantCandidates ...string) (requestAuthContext, bool) {
	if stringValue(body, "api_key") != "" {
		writeError(writer, http.StatusBadRequest, "secret_input_rejected", "local Go control plane accepts raw API key material only through Authorization: Bearer")
		return requestAuthContext{}, false
	}
	bearerSecret, bearerOK := parseBearerSecret(writer, request.Header.Get("Authorization"))
	if !bearerOK {
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
	inferredKeyID := apiKeyIDFromLocalBearerSecret(bearerSecret)
	if headerKeyID != "" && requestKeyID != "" && headerKeyID != requestKeyID {
		writeError(writer, http.StatusForbidden, "api_key_mismatch", "api_key_id/auth_key_id does not match authenticated key handle")
		return requestAuthContext{}, false
	}
	explicitKeyID := firstNonEmpty(headerKeyID, requestKeyID)
	if inferredKeyID != "" && explicitKeyID != "" && inferredKeyID != explicitKeyID {
		writeError(writer, http.StatusForbidden, "api_key_mismatch", "Authorization: Bearer credential does not match api_key_id/auth_key_id handle")
		return requestAuthContext{}, false
	}
	auth := requestAuthContext{TenantID: firstNonEmpty(headerTenant, requestTenant), APIKeyID: firstNonEmpty(explicitKeyID, inferredKeyID), BearerSecret: bearerSecret}
	if requireKey && auth.APIKeyID == "" && auth.BearerSecret == "" {
		writeError(writer, http.StatusUnauthorized, "authentication_required", "api_key_id/auth_key_id handle or Authorization: Bearer secret is required for protected local Go control-plane routes")
		return requestAuthContext{}, false
	}
	return auth, true
}

func (server *HTTPServer) preflightRequest(writer http.ResponseWriter, auth requestAuthContext, projectID, scope, operation string) bool {
	if auth.BearerSecret != "" {
		verified, err := server.service.VerifyAPIKeySecret(auth.TenantID, projectID, auth.APIKeyID, auth.BearerSecret, scope)
		if err != nil {
			writeServiceError(writer, err)
			return false
		}
		if !verified.Result.Authenticated {
			writeError(writer, http.StatusUnauthorized, "authentication_failed", "Authorization: Bearer secret did not authenticate for the required project, key, and scope")
			return false
		}
		auth.APIKeyID = verified.Result.KeyID
	}
	_, err := server.service.PreflightAPIKey(PreflightOptions{TenantID: auth.TenantID, ProjectID: projectID, KeyID: auth.APIKeyID, Scope: scope, Operation: operation, Units: 1})
	if err != nil {
		writeServiceError(writer, err)
		return false
	}
	return true
}

func parseBearerSecret(writer http.ResponseWriter, authorization string) (string, bool) {
	trimmed := strings.TrimSpace(authorization)
	if trimmed == "" {
		return "", true
	}
	parts := strings.Fields(trimmed)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") || strings.TrimSpace(parts[1]) == "" {
		writeError(writer, http.StatusBadRequest, "invalid_authorization_header", "Authorization must use Bearer scheme with exactly one credential")
		return "", false
	}
	return parts[1], true
}

func apiKeyIDFromLocalBearerSecret(secret string) string {
	trimmed := strings.TrimSpace(secret)
	if !strings.HasPrefix(trimmed, localAPIKeySecretPrefix) {
		return ""
	}
	remainder := strings.TrimPrefix(trimmed, localAPIKeySecretPrefix)
	lastUnderscore := strings.LastIndex(remainder, "_")
	if lastUnderscore <= 0 || lastUnderscore == len(remainder)-1 {
		return ""
	}
	return remainder[:lastUnderscore]
}

func (server *HTTPServer) handleProject(writer http.ResponseWriter, request *http.Request, projectID string, parts []string) {
	if len(parts) >= 2 && parts[0] == "oauth" {
		providerName := strings.ToLower(strings.TrimSpace(parts[1]))
		if providerName == "github" && server.githubOAuth != nil {
			server.handleGitHubOAuthProject(writer, request, projectID, parts[2:])
			return
		}
		if _, configured := server.oauthProviders[providerName]; configured {
			server.handleOAuthProject(writer, request, projectID, providerName, parts[2:])
			return
		}
	}
	if len(parts) >= 1 && parts[0] == "api-keys" {
		server.handleAPIKeys(writer, request, projectID, parts[1:])
		return
	}
	if request.Method == http.MethodGet && len(parts) == 1 && parts[0] == "worker-jobs" {
		server.handleListWorkerJobs(writer, request, projectID)
		return
	}
	if len(parts) >= 1 && (parts[0] == "usage" || parts[0] == "quota") {
		if request.Method == http.MethodGet && len(parts) == 1 {
			server.handleUsageSnapshot(writer, request, projectID)
			return
		}
		if request.Method == http.MethodPost && len(parts) == 2 && (parts[1] == "quotas" || parts[1] == "limits") {
			server.handleConfigureUsageQuota(writer, request, projectID)
			return
		}
	}
	if len(parts) >= 1 && parts[0] == "billing" {
		server.handleBilling(writer, request, projectID, parts[1:])
		return
	}
	if request.Method == http.MethodGet && len(parts) == 1 && parts[0] == "audit-log" {
		server.handleAuditLog(writer, request, projectID)
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
		if !server.preflightRequest(writer, auth, projectID, ScopeRunSubmit, "") {
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

func (server *HTTPServer) handleConfigureUsageQuota(writer http.ResponseWriter, request *http.Request, projectID string) {
	body, ok := readJSONBody(writer, request)
	if !ok {
		return
	}
	auth, ok := resolveRequestAuth(writer, request, body, true, stringValue(body, "tenant_id"))
	if !ok {
		return
	}
	if !server.preflightRequest(writer, auth, projectID, ScopeUsageRead, "usage_quota.configure") {
		return
	}
	result, err := server.service.ConfigureUsageQuota(auth.TenantID, projectID, stringValue(body, "operation"), intValue(body, "limit"))
	writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
}

func (server *HTTPServer) handleBilling(writer http.ResponseWriter, request *http.Request, projectID string, parts []string) {
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	tenantID := firstNonEmpty(request.URL.Query().Get("tenant_id"), stringValue(body, "tenant_id"))
	auth, ok := resolveRequestAuth(writer, request, body, true, tenantID)
	if !ok {
		return
	}
	if len(parts) >= 2 && parts[0] == "reconciliation" && parts[1] == "events" {
		server.handlePaymentReconciliation(writer, request, auth, projectID, parts[2:], body)
		return
	}
	if len(parts) >= 1 && parts[0] == "payments" {
		server.handlePaymentDomain(writer, request, auth, projectID, parts[1:], body)
		return
	}
	if request.Method == http.MethodPost && len(parts) == 1 && parts[0] == "checkout-plan" {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingWrite, "billing.checkout_plan") {
			return
		}
		billingRequest := billingPlanRequestFromBody(auth.TenantID, projectID, body)
		result, err := server.service.CreateBillingCheckoutPlan(auth.TenantID, projectID, billingRequest, IdempotencyOptions{Key: idempotencyKey(request, body), RequestID: requestID(request, body), APIKeyID: auth.APIKeyID})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodPost && len(parts) == 1 && parts[0] == "portal-plan" {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingWrite, "billing.portal_plan") {
			return
		}
		billingRequest := billingPlanRequestFromBody(auth.TenantID, projectID, body)
		result, err := server.service.CreateBillingPortalPlan(auth.TenantID, projectID, billingRequest, IdempotencyOptions{Key: idempotencyKey(request, body), RequestID: requestID(request, body), APIKeyID: auth.APIKeyID})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodPost && len(parts) == 2 && parts[0] == "webhooks" && parts[1] == "ingest" {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingWebhookIngest, "billing.webhook_ingest") {
			return
		}
		event := billingWebhookFromBody(auth.TenantID, projectID, body)
		result, err := server.service.IngestBillingWebhook(auth.TenantID, projectID, event, IdempotencyOptions{Key: idempotencyKey(request, body), RequestID: requestID(request, body), APIKeyID: auth.APIKeyID})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodGet && len(parts) == 1 && parts[0] == "ledger" {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingRead, "billing.ledger") {
			return
		}
		result, err := server.service.BillingLedger(auth.TenantID, projectID)
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) handlePaymentReconciliation(writer http.ResponseWriter, request *http.Request, auth requestAuthContext, projectID string, parts []string, body JSONMap) {
	if server.paymentReconciliation == nil {
		writeError(writer, http.StatusServiceUnavailable, "payment_reconciliation_unavailable", "payment reconciliation capability is not configured")
		return
	}
	if request.Method == http.MethodPost && len(parts) == 0 {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingWebhookIngest, "payment.reconciliation.receive") {
			return
		}
		result, err := server.paymentReconciliation.Receive(request.Context(), auth.TenantID, projectID, paymentEventEnvelopeFromBody(body))
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodGet && len(parts) == 0 {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingRead, "payment.reconciliation.list") {
			return
		}
		limit, err := intFromQueryOrBody(request.URL.Query().Get("limit"), body, "limit")
		if err != nil {
			writeServiceError(writer, fmt.Errorf("limit must be an integer"))
			return
		}
		result, err := server.paymentReconciliation.List(request.Context(), auth.TenantID, projectID, firstNonEmpty(request.URL.Query().Get("status"), stringValue(body, "status")), limit)
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) < 2 {
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
		return
	}
	provider, providerEventID := parts[0], parts[1]
	if request.Method == http.MethodGet && len(parts) == 2 {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingRead, "payment.reconciliation.get") {
			return
		}
		result, err := server.paymentReconciliation.Get(request.Context(), auth.TenantID, projectID, provider, providerEventID)
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) handlePaymentDomain(writer http.ResponseWriter, request *http.Request, auth requestAuthContext, projectID string, parts []string, body JSONMap) {
	if server.paymentDomain == nil {
		writeError(writer, http.StatusServiceUnavailable, "payment_domain_unavailable", "payment domain capability is not configured")
		return
	}
	if request.Method == http.MethodGet && len(parts) == 1 && parts[0] == "providers" {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingRead, "payment.provider.list") {
			return
		}
		writeJSON(writer, http.StatusOK, PaymentProviderCapabilitiesList())
		return
	}
	if len(parts) == 0 {
		writeError(writer, http.StatusNotFound, "not_found", "route not found")
		return
	}
	resource := parts[0]
	merchantID := firstNonEmpty(request.URL.Query().Get("merchant_id"), stringValue(body, "merchant_id"))
	provider := firstNonEmpty(request.URL.Query().Get("provider"), stringValue(body, "provider"))
	limit, err := intFromQueryOrBody(request.URL.Query().Get("limit"), body, "limit")
	if err != nil {
		writeServiceError(writer, fmt.Errorf("limit must be an integer"))
		return
	}
	if request.Method == http.MethodPost && len(parts) == 1 {
		if err := rejectPaymentCardSecrets(body); err != nil {
			writeServiceError(writer, err)
			return
		}
		scope, operation := ScopeBillingWrite, "payment."+resource+".receive"
		if resource == "notifications" || resource == "bills" {
			scope = ScopeBillingWebhookIngest
		}
		if !server.preflightRequest(writer, auth, projectID, scope, operation) {
			return
		}
		switch resource {
		case "orders":
			amount, amountErr := strictInt64Value(body, "amount")
			if amountErr != nil {
				writeServiceError(writer, amountErr)
				return
			}
			result, receiveErr := server.paymentDomain.ReceiveOrder(request.Context(), auth.TenantID, projectID, PaymentOrderReceive{
				Provider: stringValue(body, "provider"), MerchantID: merchantID, MerchantOrderID: stringValue(body, "merchant_order_id"),
				Amount: amount, Currency: stringValue(body, "currency"), Description: stringValue(body, "description"),
				Channel: stringValue(body, "channel"), CustomerRef: stringValue(body, "customer_ref"),
				AcquirerReference: stringValue(body, "acquirer_reference"), PaymentMethodTokenReference: stringValue(body, "payment_method_token_reference"),
				Metadata: mapValue(body, "metadata"),
			})
			writeEnvelopeResult(writer, http.StatusOK, result.Result, receiveErr)
		case "refunds":
			amount, amountErr := strictInt64Value(body, "amount")
			if amountErr != nil {
				writeServiceError(writer, amountErr)
				return
			}
			result, receiveErr := server.paymentDomain.ReceiveRefund(request.Context(), auth.TenantID, projectID, PaymentRefundReceive{
				Provider: stringValue(body, "provider"), MerchantID: merchantID, MerchantRefundID: stringValue(body, "merchant_refund_id"),
				MerchantOrderID: stringValue(body, "merchant_order_id"), Amount: amount, Currency: stringValue(body, "currency"),
				Reason: stringValue(body, "reason"), Metadata: mapValue(body, "metadata"),
			})
			writeEnvelopeResult(writer, http.StatusOK, result.Result, receiveErr)
		case "notifications":
			occurredAt, timeErr := optionalPaymentTime(body, "occurred_at")
			if timeErr != nil {
				writeServiceError(writer, timeErr)
				return
			}
			result, receiveErr := server.paymentDomain.ReceiveNotification(request.Context(), auth.TenantID, projectID, PaymentNotificationReceive{
				Provider: stringValue(body, "provider"), MerchantID: merchantID, ProviderEventID: stringValue(body, "provider_event_id"),
				EventType: stringValue(body, "event_type"), ResourceType: stringValue(body, "resource_type"),
				MerchantOrderID: stringValue(body, "merchant_order_id"), MerchantRefundID: stringValue(body, "merchant_refund_id"),
				ProviderObjectID: stringValue(body, "provider_object_id"), ProviderStatus: stringValue(body, "provider_status"),
				PayloadSHA256: stringValue(body, "payload_sha256"), HeadersSHA256: stringValue(body, "headers_sha256"), OccurredAt: occurredAt,
			})
			writeEnvelopeResult(writer, http.StatusOK, result.Result, receiveErr)
		case "bills":
			amount, amountErr := strictInt64Value(body, "amount")
			if amountErr != nil {
				writeServiceError(writer, amountErr)
				return
			}
			occurredAt, timeErr := optionalPaymentTime(body, "occurred_at")
			if timeErr != nil {
				writeServiceError(writer, timeErr)
				return
			}
			result, receiveErr := server.paymentDomain.ReceiveBillEntry(request.Context(), auth.TenantID, projectID, PaymentBillEntryReceive{
				Provider: stringValue(body, "provider"), MerchantID: merchantID, BillEntryID: stringValue(body, "bill_entry_id"),
				BillDate: stringValue(body, "bill_date"), BillKind: stringValue(body, "bill_kind"), TransactionID: stringValue(body, "transaction_id"),
				MerchantOrderID: stringValue(body, "merchant_order_id"), MerchantRefundID: stringValue(body, "merchant_refund_id"),
				Amount: amount, Currency: stringValue(body, "currency"), ProviderStatus: stringValue(body, "provider_status"),
				SourceSHA256: stringValue(body, "source_sha256"), OccurredAt: occurredAt,
			})
			writeEnvelopeResult(writer, http.StatusOK, result.Result, receiveErr)
		default:
			writeError(writer, http.StatusNotFound, "not_found", "route not found")
		}
		return
	}
	if request.Method == http.MethodGet && len(parts) == 1 {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingRead, "payment."+resource+".list") {
			return
		}
		switch resource {
		case "orders":
			result, listErr := server.paymentDomain.ListOrders(request.Context(), auth.TenantID, projectID, merchantID, provider, firstNonEmpty(request.URL.Query().Get("status"), stringValue(body, "status")), limit)
			writeEnvelopeResult(writer, http.StatusOK, result.Result, listErr)
		case "refunds":
			result, listErr := server.paymentDomain.ListRefunds(request.Context(), auth.TenantID, projectID, merchantID, provider, firstNonEmpty(request.URL.Query().Get("status"), stringValue(body, "status")), limit)
			writeEnvelopeResult(writer, http.StatusOK, result.Result, listErr)
		case "notifications":
			result, listErr := server.paymentDomain.ListNotifications(request.Context(), auth.TenantID, projectID, merchantID, provider, limit)
			writeEnvelopeResult(writer, http.StatusOK, result.Result, listErr)
		case "bills":
			result, listErr := server.paymentDomain.ListBillEntries(request.Context(), auth.TenantID, projectID, merchantID, provider, firstNonEmpty(request.URL.Query().Get("match_status"), stringValue(body, "match_status")), limit)
			writeEnvelopeResult(writer, http.StatusOK, result.Result, listErr)
		default:
			writeError(writer, http.StatusNotFound, "not_found", "route not found")
		}
		return
	}
	if request.Method == http.MethodGet && len(parts) == 3 {
		if !server.preflightRequest(writer, auth, projectID, ScopeBillingRead, "payment."+resource+".get") {
			return
		}
		provider, id := parts[1], parts[2]
		switch resource {
		case "orders":
			result, getErr := server.paymentDomain.GetOrder(request.Context(), auth.TenantID, projectID, merchantID, provider, id)
			writeEnvelopeResult(writer, http.StatusOK, result.Result, getErr)
		case "refunds":
			result, getErr := server.paymentDomain.GetRefund(request.Context(), auth.TenantID, projectID, merchantID, provider, id)
			writeEnvelopeResult(writer, http.StatusOK, result.Result, getErr)
		case "notifications":
			result, getErr := server.paymentDomain.GetNotification(request.Context(), auth.TenantID, projectID, merchantID, provider, id)
			writeEnvelopeResult(writer, http.StatusOK, result.Result, getErr)
		case "bills":
			result, getErr := server.paymentDomain.GetBillEntry(request.Context(), auth.TenantID, projectID, merchantID, provider, id)
			writeEnvelopeResult(writer, http.StatusOK, result.Result, getErr)
		default:
			writeError(writer, http.StatusNotFound, "not_found", "route not found")
		}
		return
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) handleAPIKeys(writer http.ResponseWriter, request *http.Request, projectID string, parts []string) {
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	query := request.URL.Query()
	tenantID := firstNonEmpty(query.Get("tenant_id"), stringValue(body, "tenant_id"))
	auth, ok := resolveRequestAuth(writer, request, body, false, tenantID)
	if !ok {
		return
	}
	if request.Method == http.MethodPost && len(parts) == 0 {
		if !server.allowBootstrapFirstAPIKey(writer, auth, tenantID, projectID, stringSliceFromAny(body["scopes"])) {
			return
		}
		result, err := server.service.CreateAPIKey(tenantID, projectID, CreateAPIKeyOptions{Name: stringValue(body, "name"), Scopes: stringSliceFromAny(body["scopes"]), KeyID: stringValue(body, "key_id"), AuthKeyID: stringValue(body, "auth_key_id"), RevealSecret: boolValue(body, "reveal_secret")})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodGet && len(parts) == 0 {
		if !server.preflightRequest(writer, auth, projectID, ScopeAPIKeyRead, "api_key.list") {
			return
		}
		result, err := server.service.ListAPIKeys(auth.TenantID, projectID)
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodGet && len(parts) == 1 && parts[0] == "rate-limits" {
		if !server.preflightRequest(writer, auth, projectID, ScopeAPIKeyRead, "api_key.rate_limit.snapshot") {
			return
		}
		keyID := firstNonEmpty(query.Get("key_id"), stringValue(body, "key_id"))
		result, err := server.service.APIKeyRateLimitSnapshot(auth.TenantID, projectID, keyID)
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if request.Method == http.MethodPost && len(parts) == 1 && parts[0] == "preflight" {
		if !server.preflightRequest(writer, auth, projectID, ScopeAPIKeyPreflight, "api_key.preflight") {
			return
		}
		result, err := server.service.PreflightAPIKey(PreflightOptions{TenantID: auth.TenantID, ProjectID: projectID, KeyID: firstNonEmpty(stringValue(body, "key_id"), stringValue(body, "api_key_id"), stringValue(body, "auth_key_id")), Scope: stringValue(body, "scope"), Operation: stringValue(body, "operation"), Units: intValue(body, "units")})
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) == 2 && parts[1] == "revoke" && request.Method == http.MethodPost {
		if !server.preflightRequest(writer, auth, projectID, ScopeAPIKeyWrite, "api_key.revoke") {
			return
		}
		result, err := server.service.RevokeAPIKey(auth.TenantID, projectID, parts[0])
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) == 2 && parts[1] == "verify" && request.Method == http.MethodPost {
		result, err := server.service.VerifyAPIKeySecret(tenantID, projectID, parts[0], stringValue(body, "secret"), stringValue(body, "scope"))
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	if len(parts) == 2 && parts[1] == "rate-limit" && request.Method == http.MethodPost {
		if !server.preflightRequest(writer, auth, projectID, ScopeAPIKeyWrite, "api_key.rate_limit.configure") {
			return
		}
		result, err := server.service.ConfigureAPIKeyRateLimit(auth.TenantID, projectID, parts[0], stringValue(body, "operation"), intValue(body, "limit"))
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
	}
	writeError(writer, http.StatusNotFound, "not_found", "route not found")
}

func (server *HTTPServer) allowBootstrapFirstAPIKey(writer http.ResponseWriter, auth requestAuthContext, tenantID, projectID string, requestedScopes []string) bool {
	if auth.APIKeyID != "" || auth.BearerSecret != "" {
		return server.preflightRequest(writer, auth, projectID, ScopeAPIKeyWrite, "api_key.create")
	}
	if !scopeAllowed(requestedScopes, ScopeAPIKeyWrite) {
		writeError(writer, http.StatusUnauthorized, "authentication_required", "first unauthenticated API key must include api_key:write scope; later API-key creation requires admin auth")
		return false
	}
	listed, err := server.service.ListAPIKeys(tenantID, projectID)
	if err != nil {
		writeServiceError(writer, err)
		return false
	}
	if listed.Result.Count > 0 {
		writeError(writer, http.StatusUnauthorized, "authentication_required", "API-key creation requires Authorization: Bearer admin credentials after the first bootstrap key")
		return false
	}
	return true
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

func (server *HTTPServer) handleAuditLog(writer http.ResponseWriter, request *http.Request, projectID string) {
	body, ok := readJSONBodyAllowGET(writer, request)
	if !ok {
		return
	}
	query := request.URL.Query()
	auth, ok := resolveRequestAuth(writer, request, body, true, firstNonEmpty(query.Get("tenant_id"), stringValue(body, "tenant_id")))
	if !ok {
		return
	}
	if !server.preflightRequest(writer, auth, projectID, ScopeAuditRead, "audit_log") {
		return
	}
	limit, err := intFromQueryOrBody(query.Get("limit"), body, "limit")
	if err != nil {
		writeError(writer, http.StatusBadRequest, "validation_error", "limit must be an integer")
		return
	}
	result, err := server.service.AuditLog(auth.TenantID, projectID, AuditLogOptions{RunID: firstNonEmpty(query.Get("run_id"), stringValue(body, "run_id")), ActionPrefix: firstNonEmpty(query.Get("action_prefix"), stringValue(body, "action_prefix")), AuthKeyID: auth.APIKeyID, Limit: limit})
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
		case "lifecycle":
			if request.Method == http.MethodGet {
				if !server.preflightRequest(writer, auth, projectID, ScopeRunLifecycleRead, "lifecycle") {
					return
				}
				result, err := server.service.RunLifecycle(tenantID, projectID, runID)
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
		case "release-evidence":
			if request.Method == http.MethodGet {
				if !server.preflightRequest(writer, auth, projectID, ScopeEvidenceRead, "release_evidence") {
					return
				}
				result, err := server.service.BuildReleaseEvidencePacket(tenantID, projectID, runID)
				writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
				return
			}
		}
	}
	if len(parts) == 2 && parts[0] == "release-evidence" && parts[1] == "verify" && request.Method == http.MethodPost {
		if !server.preflightRequest(writer, auth, projectID, ScopeEvidenceRead, "release_evidence.verify") {
			return
		}
		packet := mapValue(body, "packet")
		if len(packet) == 0 {
			packet = body
		}
		result, err := server.service.VerifyReleaseEvidencePacket(tenantID, projectID, runID, packet)
		writeEnvelopeResult(writer, http.StatusOK, result.Result, err)
		return
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

type RouteManifestEntry struct {
	Method       string   `json:"method"`
	Path         string   `json:"path"`
	Route        string   `json:"route"`
	Operation    string   `json:"operation"`
	Category     string   `json:"category"`
	AuthRequired bool     `json:"auth_required"`
	Scopes       []string `json:"scopes"`
	PublicSafe   bool     `json:"public_safe"`
}

type ScopeManifestEntry struct {
	Route     string `json:"route"`
	Operation string `json:"operation"`
}

type RouteScopeDocs struct {
	SchemaVersion       string                `json:"schema_version"`
	PublicSafe          bool                  `json:"public_safe"`
	RawPayloadsIncluded bool                  `json:"raw_payloads_included"`
	Source              string                `json:"source"`
	RouteGroups         []RouteScopeDocGroup  `json:"route_groups"`
	PlanLimits          []RouteScopeDocPlan   `json:"plan_limits"`
	PlanMetrics         []RouteScopeDocMetric `json:"plan_metrics"`
	Notes               []string              `json:"notes"`
}

type RouteScopeDocGroup struct {
	Name       string   `json:"name"`
	Operations []string `json:"operations"`
	Routes     []string `json:"routes"`
	Scopes     []string `json:"scopes"`
}

type RouteScopeDocPlan struct {
	Plan      string                   `json:"plan"`
	CapMode   string                   `json:"cap_mode"`
	Limits    []RouteScopeDocPlanLimit `json:"limits"`
	PublicURL string                   `json:"public_url"`
}

type RouteScopeDocPlanLimit struct {
	Metric string `json:"metric"`
	Limit  int    `json:"limit"`
	Unit   string `json:"unit"`
}

type RouteScopeDocMetric struct {
	Metric      string   `json:"metric"`
	Unit        string   `json:"unit"`
	Operations  []string `json:"operations"`
	Description string   `json:"description"`
}

func GoRouteManifest(backendName ...string) JSONMap {
	backingStore := "memory_service_v0"
	if len(backendName) > 0 && strings.TrimSpace(backendName[0]) != "" {
		backingStore = strings.TrimSpace(backendName[0])
	}
	routeEntries := GoRouteManifestEntries()
	routes := GoRouteManifestRoutes(routeEntries)
	scopeManifest := GoScopeManifest(routeEntries)
	routeScopeDocs := GoRouteScopeDocs(routeEntries)
	return JSONMap{"schema_version": ControlPlaneSchemaVersion, "manifest_schema_version": "ashr.clone.go_route_scope_manifest.v1", "routes": routes, "route_manifest": routeEntries, "scope_manifest": scopeManifest, "route_scope_docs": routeScopeDocs, "route_count": len(routeEntries), "go_owned": true, "backing_store": backingStore, "raw_payloads_included": false, "public_safe": true}
}

func GoRouteManifestEntries() []RouteManifestEntry {
	entries := []RouteManifestEntry{
		goPublicRoute("GET", "/health", "health", "system"),
		goPublicRoute("GET", "/healthz", "health", "system"),
		goPublicRoute("GET", "/v1/healthz", "health", "system"),
		goPublicRoute("GET", "/openapi.json", "openapi", "system"),
		goPublicRoute("GET", "/v1/openapi.json", "openapi", "system"),
		goPublicRoute("GET", "/v1/identity/providers", "identity.providers.list", "identity"),
		goPublicRoute("POST", "/v1/identity/registration/start", "identity.registration.start", "identity"),
		goPublicRoute("POST", "/v1/identity/registration/complete", "identity.registration.complete", "identity"),
		goPublicRoute("POST", "/v1/identity/login/start", "identity.login.start", "identity"),
		goPublicRoute("POST", "/v1/identity/login/complete", "identity.login.complete", "identity"),
		goPublicRoute("POST", "/v1/identity/registration/email/begin", "identity.registration.email.begin", "identity"),
		goPublicRoute("POST", "/v1/identity/registration/email/complete", "identity.registration.email.complete", "identity"),
		goPublicRoute("POST", "/v1/identity/login/email/begin", "identity.login.email.begin", "identity"),
		goPublicRoute("POST", "/v1/identity/login/email/complete", "identity.login.email.complete", "identity"),
		goPublicRoute("POST", "/v1/identity/oauth/begin", "identity.oauth.begin", "identity"),
		goPublicRoute("POST", "/v1/identity/oauth/complete", "identity.oauth.complete", "identity"),
		goPublicRoute("POST", "/v1/identity/mfa/complete", "identity.mfa.complete", "identity"),
		goPublicRoute("POST", "/v1/identity/credentials/bind", "identity.credentials.bind", "identity"),
		goPublicRoute("POST", "/v1/identity/sessions/revoke", "identity.sessions.revoke", "identity"),
		goPublicRoute("GET", "/v1/me", "identity.me", "identity"),
		goScopedRoute("GET", "/v1/accounts/{account_id}", "identity.account.get", "identity"),
		goScopedRoute("GET", "/v1/accounts/{account_id}/credentials", "identity.credentials.list", "identity"),
		goScopedRoute("GET", "/v1/accounts/{account_id}/memberships", "identity.memberships.list", "identity"),
		goScopedRoute("POST", "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh", "identity.browser_session.refresh", "identity"),
		// Reserved fail-closed contracts:
		// POST /v1/accounts/{account_id}/credentials/{provider}/link
		// DELETE /v1/accounts/{account_id}/credentials/{credential_id}/unlink
		// They stay out of the public manifest until a provider-verified
		// server-side assertion boundary is available.
		goScopedRoute("GET", "/v1/projects/{project_id}/oauth/github/start", "oauth.github.start", "oauth"),
		goScopedRoute("POST", "/v1/projects/{project_id}/oauth/github/start", "oauth.github.start", "oauth"),
		goPublicRoute("GET", "/oauth/github/callback", "oauth.github.callback", "oauth"),
		goScopedRoute("GET", "/v1/projects/{project_id}/oauth/github/connection", "oauth.github.connection", "oauth"),
		goScopedRoute("POST", "/v1/projects/{project_id}/oauth/github/disconnect", "oauth.github.disconnect", "oauth"),
		goScopedRoute("DELETE", "/v1/projects/{project_id}/oauth/github/disconnect", "oauth.github.disconnect", "oauth"),
		goScopedRoute("GET", "/v1/projects/{project_id}/oauth/google/start", "oauth.google.start", "oauth"),
		goScopedRoute("POST", "/v1/projects/{project_id}/oauth/google/start", "oauth.google.start", "oauth"),
		goPublicRoute("GET", "/oauth/google/callback", "oauth.google.callback", "oauth"),
		goScopedRoute("GET", "/v1/projects/{project_id}/oauth/google/connection", "oauth.google.connection", "oauth"),
		goScopedRoute("POST", "/v1/projects/{project_id}/oauth/google/disconnect", "oauth.google.disconnect", "oauth"),
		goScopedRoute("DELETE", "/v1/projects/{project_id}/oauth/google/disconnect", "oauth.google.disconnect", "oauth"),
		goPublicRoute("POST", "/bootstrap", "bootstrap_project", "bootstrap"),
		goPublicRoute("POST", "/v1/bootstrap", "bootstrap_project", "bootstrap"),
		goScopedRoute("POST", "/v1/projects/{project_id}/api-keys", "api_key.create", "auth", ScopeAPIKeyWrite),
		goScopedRoute("GET", "/v1/projects/{project_id}/api-keys", "api_key.list", "auth", ScopeAPIKeyRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/api-keys/preflight", "api_key.preflight", "auth", ScopeAPIKeyPreflight),
		goScopedRoute("GET", "/v1/projects/{project_id}/api-keys/rate-limits", "api_key.rate_limit.snapshot", "auth", ScopeAPIKeyRead),
		goPublicRoute("POST", "/v1/projects/{project_id}/api-keys/{key_id}/verify", "api_key.verify", "auth"),
		goScopedRoute("POST", "/v1/projects/{project_id}/api-keys/{key_id}/revoke", "api_key.revoke", "auth", ScopeAPIKeyWrite),
		goScopedRoute("POST", "/v1/projects/{project_id}/api-keys/{key_id}/rate-limit", "api_key.rate_limit.configure", "auth", ScopeAPIKeyWrite),
		goScopedRoute("POST", "/v1/projects/{project_id}/sdk-submit", "sdk_submit", "run", ScopeRunSubmit),
		goScopedRoute("POST", "/v1/projects/{project_id}/runs/submit", "sdk_submit", "run", ScopeRunSubmit),
		goScopedRoute("GET", "/v1/projects/{project_id}/usage", "usage", "billing", ScopeUsageRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/quota", "usage", "billing", ScopeUsageRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/usage/quotas", "usage_quota.configure", "billing", ScopeUsageRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/quota/limits", "usage_quota.configure", "billing", ScopeUsageRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/billing/checkout-plan", "billing.checkout_plan", "billing", ScopeBillingWrite),
		goScopedRoute("POST", "/v1/projects/{project_id}/billing/portal-plan", "billing.portal_plan", "billing", ScopeBillingWrite),
		goScopedRoute("POST", "/v1/projects/{project_id}/billing/webhooks/ingest", "billing.webhook_ingest", "billing", ScopeBillingWebhookIngest),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/ledger", "billing.ledger", "billing", ScopeBillingRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/billing/reconciliation/events", "payment.reconciliation.receive", "billing", ScopeBillingWebhookIngest),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/reconciliation/events", "payment.reconciliation.list", "billing", ScopeBillingRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/reconciliation/events/{provider}/{event_id}", "payment.reconciliation.get", "billing", ScopeBillingRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/payments/providers", "payment.provider.list", "billing", ScopeBillingRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/billing/payments/orders", "payment.orders.receive", "billing", ScopeBillingWrite),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/payments/orders", "payment.orders.list", "billing", ScopeBillingRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/payments/orders/{provider}/{merchant_order_id}", "payment.orders.get", "billing", ScopeBillingRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/billing/payments/refunds", "payment.refunds.receive", "billing", ScopeBillingWrite),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/payments/refunds", "payment.refunds.list", "billing", ScopeBillingRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/payments/refunds/{provider}/{merchant_refund_id}", "payment.refunds.get", "billing", ScopeBillingRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/billing/payments/notifications", "payment.notifications.receive", "billing", ScopeBillingWebhookIngest),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/payments/notifications", "payment.notifications.list", "billing", ScopeBillingRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/payments/notifications/{provider}/{event_id}", "payment.notifications.get", "billing", ScopeBillingRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/billing/payments/bills", "payment.bills.receive", "billing", ScopeBillingWebhookIngest),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/payments/bills", "payment.bills.list", "billing", ScopeBillingRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/billing/payments/bills/{provider}/{bill_entry_id}", "payment.bills.get", "billing", ScopeBillingRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/audit-log", "audit_log", "audit", ScopeAuditRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/audit-chain/verify", "audit.chain.verify", "audit", ScopeAuditRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/audit-chain/verify", "audit.chain.verify", "audit", ScopeAuditRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/runs/{run_id}/upload", "upload_run", "run", ScopeRunUpload),
		goScopedRoute("POST", "/v1/projects/{project_id}/runs/{run_id}/trace-events", "ingest_trace", "trace", ScopeTraceIngest),
		goScopedRoute("POST", "/v1/projects/{project_id}/runs/{run_id}/artifact-manifests", "artifact_manifest", "artifact", ScopeArtifactManifestWrite),
		goScopedRoute("GET", "/v1/projects/{project_id}/runs/{run_id}/artifact-manifests", "artifact_manifests", "artifact", ScopeArtifactManifestRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/runs/{run_id}/lifecycle", "lifecycle", "run", ScopeRunLifecycleRead),
		goScopedRoute("GET", "/v1/projects/{project_id}/runs/{run_id}/release-evidence", "release_evidence", "release", ScopeEvidenceRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/runs/{run_id}/release-evidence/verify", "release_evidence.verify", "release", ScopeEvidenceRead),
		goScopedRoute("POST", "/v1/projects/{project_id}/worker-jobs/enqueue", "worker.job.enqueue", "worker", ScopeWorkerJobEnqueue),
		goScopedRoute("POST", "/v1/projects/{project_id}/worker-jobs/lease", "worker.job.lease", "worker", ScopeWorkerJobLease),
		goScopedRoute("GET", "/v1/projects/{project_id}/worker-jobs", "worker.job.list", "worker", ScopeWorkerJobList),
		goScopedRoute("POST", "/v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat", "worker.job.heartbeat", "worker", ScopeWorkerJobLease),
		goScopedRoute("POST", "/v1/projects/{project_id}/worker-jobs/{job_id}/complete", "worker.job.complete", "worker", ScopeWorkerJobComplete),
		goScopedRoute("POST", "/v1/projects/{project_id}/worker-jobs/{job_id}/fail", "worker.job.fail", "worker", ScopeWorkerJobFail),
	}
	sort.Slice(entries, func(i, j int) bool {
		if entries[i].Route == entries[j].Route {
			return entries[i].Operation < entries[j].Operation
		}
		return entries[i].Route < entries[j].Route
	})
	return entries
}

func GoRouteManifestRoutes(entries []RouteManifestEntry) []string {
	routes := make([]string, 0, len(entries))
	for _, entry := range entries {
		routes = append(routes, entry.Route)
	}
	sort.Strings(routes)
	return routes
}

func GoScopeManifest(entries []RouteManifestEntry) map[string][]ScopeManifestEntry {
	manifest := map[string][]ScopeManifestEntry{}
	for _, entry := range entries {
		for _, scope := range entry.Scopes {
			manifest[scope] = append(manifest[scope], ScopeManifestEntry{Route: entry.Route, Operation: entry.Operation})
		}
	}
	for scope := range manifest {
		scopeEntries := manifest[scope]
		sort.Slice(scopeEntries, func(i, j int) bool {
			if scopeEntries[i].Route == scopeEntries[j].Route {
				return scopeEntries[i].Operation < scopeEntries[j].Operation
			}
			return scopeEntries[i].Route < scopeEntries[j].Route
		})
		manifest[scope] = scopeEntries
	}
	return manifest
}

func GoRouteScopeDocs(entries []RouteManifestEntry) RouteScopeDocs {
	groups := []RouteScopeDocGroup{
		goRouteScopeDocGroup(entries, "usage_quota", []string{"usage", "usage_quota.configure"}),
		goRouteScopeDocGroup(entries, "billing_contract", []string{"billing.checkout_plan", "billing.portal_plan", "billing.webhook_ingest", "billing.ledger", "payment.reconciliation.receive", "payment.reconciliation.list", "payment.reconciliation.get"}),
		goRouteScopeDocGroup(entries, "run_lifecycle", []string{"lifecycle"}),
		goRouteScopeDocGroup(entries, "audit", []string{"audit.chain.verify", "audit_log"}),
	}
	return RouteScopeDocs{
		SchemaVersion:       "ashr.clone.go_route_scope_docs.v1",
		PublicSafe:          true,
		RawPayloadsIncluded: false,
		Source:              "generated_from_go_route_manifest",
		RouteGroups:         groups,
		PlanLimits:          goPublicPlanLimits(),
		PlanMetrics: []RouteScopeDocMetric{
			{Metric: "graded_scenarios", Unit: "scenario", Operations: []string{"sdk_submit"}, Description: "Run submissions counted as graded scenario units."},
			{Metric: "observations", Unit: "observation", Operations: []string{"ingest_trace"}, Description: "Trace observation rows accepted by the runtime."},
			{Metric: "voice_minutes", Unit: "minute", Operations: []string{"upload_run", "ingest_trace"}, Description: "Voice/media usage documented for quota parity; local runtime records route coverage only."},
			{Metric: "projects", Unit: "project", Operations: []string{"bootstrap_project"}, Description: "Project-count limit reference for billing documentation parity."},
		},
		Notes: []string{
			"plan limits are public documentation references, not secret billing state",
			"route groups are derived from GoRouteManifestEntries",
			"captured HTTP bodies and tenant data are intentionally excluded",
		},
	}
}

func goRouteScopeDocGroup(entries []RouteManifestEntry, name string, operations []string) RouteScopeDocGroup {
	operationSet := map[string]bool{}
	for _, operation := range operations {
		operationSet[operation] = true
	}
	routes := []string{}
	scopes := []string{}
	seenScopes := map[string]bool{}
	seenOperations := map[string]bool{}
	for _, entry := range entries {
		if !operationSet[entry.Operation] {
			continue
		}
		routes = append(routes, entry.Route)
		seenOperations[entry.Operation] = true
		for _, scope := range entry.Scopes {
			if seenScopes[scope] {
				continue
			}
			seenScopes[scope] = true
			scopes = append(scopes, scope)
		}
	}
	resolvedOperations := make([]string, 0, len(seenOperations))
	for operation := range seenOperations {
		resolvedOperations = append(resolvedOperations, operation)
	}
	sort.Strings(resolvedOperations)
	sort.Strings(routes)
	sort.Strings(scopes)
	return RouteScopeDocGroup{Name: name, Operations: resolvedOperations, Routes: routes, Scopes: scopes}
}

func goPublicPlanLimits() []RouteScopeDocPlan {
	return []RouteScopeDocPlan{
		{
			Plan:      "Developer",
			CapMode:   "hard_limit",
			PublicURL: "https://www.ashr.io/pricing",
			Limits: []RouteScopeDocPlanLimit{
				{Metric: "graded_scenarios", Limit: 5000, Unit: "scenario"},
				{Metric: "observations", Limit: 250000, Unit: "observation"},
				{Metric: "voice_minutes", Limit: 1000, Unit: "minute"},
				{Metric: "projects", Limit: 1, Unit: "project"},
			},
		},
		{
			Plan:      "Startup",
			CapMode:   "overage_billing",
			PublicURL: "https://www.ashr.io/pricing",
			Limits: []RouteScopeDocPlanLimit{
				{Metric: "graded_scenarios", Limit: 100000, Unit: "scenario"},
				{Metric: "observations", Limit: 10000000, Unit: "observation"},
				{Metric: "voice_minutes", Limit: 50000, Unit: "minute"},
				{Metric: "projects", Limit: 0, Unit: "unlimited"},
			},
		},
	}
}

func goPublicRoute(method, path, operation, category string) RouteManifestEntry {
	return goRoute(method, path, operation, category, false, nil)
}

func goAdminRoute(method, path, operation, category string) RouteManifestEntry {
	return goRoute(method, path, operation, category, false, nil)
}

func goScopedRoute(method, path, operation, category string, scopes ...string) RouteManifestEntry {
	return goRoute(method, path, operation, category, true, scopes)
}

func goRoute(method, path, operation, category string, authRequired bool, scopes []string) RouteManifestEntry {
	return RouteManifestEntry{Method: method, Path: path, Route: method + " " + path, Operation: operation, Category: category, AuthRequired: authRequired, Scopes: sortedUniqueStrings(scopes), PublicSafe: true}
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
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		writeError(writer, http.StatusBadRequest, "invalid_json", "request body must contain exactly one JSON object")
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
	var paymentConflict PaymentDomainConflictError
	var paymentVerificationRequired PaymentNotificationVerificationRequiredError
	var reconciliationConflict PaymentReconciliationConflictError
	var reconciliationTransition PaymentReconciliationTransitionError
	var notFound NotFoundError
	var authz AuthzError
	var quota QuotaExceededError
	switch {
	case errors.As(err, &conflict):
		writeError(writer, http.StatusConflict, "idempotency_conflict", conflict.Error())
	case errors.As(err, &paymentConflict):
		writeError(writer, http.StatusConflict, "payment_domain_conflict", paymentConflict.Error())
	case errors.As(err, &paymentVerificationRequired):
		writeError(writer, http.StatusForbidden, "trusted_payment_verification_required", paymentVerificationRequired.Error())
	case errors.As(err, &reconciliationConflict):
		writeError(writer, http.StatusConflict, "payment_reconciliation_conflict", reconciliationConflict.Error())
	case errors.As(err, &reconciliationTransition):
		writeError(writer, http.StatusConflict, "payment_reconciliation_transition_conflict", reconciliationTransition.Error())
	case errors.As(err, &notFound):
		writeError(writer, http.StatusNotFound, "not_found", notFound.Error())
	case errors.As(err, &authz):
		code := authz.Code
		if code == "" {
			code = "forbidden"
		}
		writeError(writer, http.StatusForbidden, code, authz.Error())
	case errors.As(err, &quota):
		writeQuotaExceeded(writer, quota)
	default:
		writeError(writer, http.StatusBadRequest, "validation_error", err.Error())
	}
}

func writeError(writer http.ResponseWriter, status int, code, message string) {
	writeJSON(writer, status, JSONMap{"schema_version": ControlPlaneSchemaVersion, "status": "error", "error": JSONMap{"code": code, "message": RedactSensitive(message)}})
}

func writeQuotaExceeded(writer http.ResponseWriter, quota QuotaExceededError) {
	detail := quota.PublicSchema()
	writeJSON(writer, http.StatusTooManyRequests, JSONMap{"schema_version": ControlPlaneSchemaVersion, "status": "error", "error": detail})
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

func billingPlanRequestFromBody(tenantID, projectID string, body JSONMap) BillingPlanRequest {
	return BillingPlanRequest{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, PlanID: stringValue(body, "plan_id"), BillingCycle: stringValue(body, "billing_cycle"), ProviderConfig: mapValue(body, "provider_config"), CustomerRef: stringValue(body, "customer_ref"), Price: mapValue(body, "price"), SuccessURL: stringValue(body, "success_url"), CancelURL: stringValue(body, "cancel_url"), ReturnURL: stringValue(body, "return_url"), Metadata: mapValue(body, "metadata")}
}

func billingWebhookFromBody(tenantID, projectID string, body JSONMap) BillingWebhookIngest {
	return BillingWebhookIngest{SchemaVersion: ControlPlaneSchemaVersion, TenantID: tenantID, ProjectID: projectID, EventID: stringValue(body, "event_id"), EventType: stringValue(body, "event_type"), Provider: stringValue(body, "provider"), Mode: stringValue(body, "mode"), PlanID: stringValue(body, "plan_id"), CustomerRef: stringValue(body, "customer_ref"), Status: stringValue(body, "status"), PayloadSHA256: stringValue(body, "payload_sha256"), SignatureHeaderPresent: boolValue(body, "signature_header_present"), WebhookSecretRef: stringValue(body, "webhook_secret_ref"), Livemode: boolValue(body, "livemode"), Metadata: mapValue(body, "metadata")}
}

func paymentEventEnvelopeFromBody(body JSONMap) PaymentEventHashEnvelope {
	return PaymentEventHashEnvelope{
		Provider:        stringValue(body, "provider"),
		ProviderEventID: firstNonEmpty(stringValue(body, "provider_event_id"), stringValue(body, "event_id")),
		EventType:       stringValue(body, "event_type"),
		PayloadSHA256:   stringValue(body, "payload_sha256"),
		HeadersSHA256:   stringValue(body, "headers_sha256"),
	}
}

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

func strictInt64Value(body JSONMap, key string) (int64, error) {
	value, ok := body[key]
	if !ok {
		return 0, fmt.Errorf("%s is required", key)
	}
	switch typed := value.(type) {
	case json.Number:
		result, err := typed.Int64()
		if err != nil {
			return 0, fmt.Errorf("%s must be an integer within int64 range", key)
		}
		return result, nil
	case int64:
		return typed, nil
	case int:
		return int64(typed), nil
	default:
		return 0, fmt.Errorf("%s must be an integer within int64 range", key)
	}
}

func optionalPaymentTime(body JSONMap, key string) (time.Time, error) {
	raw := strings.TrimSpace(stringValue(body, key))
	if raw == "" {
		return time.Time{}, nil
	}
	value, err := time.Parse(time.RFC3339Nano, raw)
	if err != nil {
		return time.Time{}, fmt.Errorf("%s must be an RFC3339 timestamp", key)
	}
	return value.UTC(), nil
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
