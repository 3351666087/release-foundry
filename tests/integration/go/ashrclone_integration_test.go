package gointegration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	ashrclone "github.com/ashr-labs/ashr/packages/go/ashrclone"
)

func TestPublicChinaPaymentNotificationCannotForgeProviderStatus(t *testing.T) {
	controlPlane := ashrclone.NewMemoryService()
	if _, err := controlPlane.BootstrapProject("Tenant", "Payments", ashrclone.Dataset{Name: "Dataset"}, "tenant_payment", "project_payment"); err != nil {
		t.Fatal(err)
	}
	if _, err := controlPlane.CreateAPIKey("tenant_payment", "project_payment", ashrclone.CreateAPIKeyOptions{
		KeyID: "key_webhook", Name: "Webhook", Scopes: []string{ashrclone.ScopeBillingWebhookIngest},
	}); err != nil {
		t.Fatal(err)
	}
	payments, err := ashrclone.NewPaymentDomainService(ashrclone.NewMemoryPaymentDomainRepository())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := payments.ReceiveOrder(context.Background(), "tenant_payment", "project_payment", ashrclone.PaymentOrderReceive{
		Provider: ashrclone.PaymentProviderWeChatPay, MerchantID: "merchant_payment", MerchantOrderID: "order_payment",
		Amount: 100, Currency: "CNY", Channel: "native",
	}); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(ashrclone.NewHTTPServerWithOptions(controlPlane, ashrclone.HTTPServerOptions{
		BackendName: "memory_service_v0", BackendReady: true, PaymentDomain: payments,
	}))
	defer server.Close()

	for _, attack := range []ashrclone.JSONMap{
		{
			"tenant_id": "tenant_payment", "api_key_id": "key_webhook",
			"provider": "wechat_pay", "merchant_id": "merchant_payment", "provider_event_id": "forged-success",
			"event_type": "TRANSACTION.SUCCESS", "resource_type": "order", "merchant_order_id": "order_payment",
			"provider_status": "SUCCESS", "payload_sha256": strings.Repeat("a", 64),
		},
		{
			"tenant_id": "tenant_payment", "api_key_id": "key_webhook",
			"provider": "wechat_pay", "merchant_id": "merchant_payment", "provider_event_id": "forged-artifact",
			"event_type": "TRANSACTION.SUCCESS", "resource_type": "order", "merchant_order_id": "order_payment",
			"provider_status": "SUCCESS", "payload_sha256": strings.Repeat("b", 64),
			"verification": ashrclone.JSONMap{
				"verifier_id": "attacker", "verifier_version": "999", "artifact_mac_sha256": strings.Repeat("c", 64),
			},
		},
	} {
		payload, _ := json.Marshal(attack)
		response, requestErr := http.Post(server.URL+"/v1/projects/project_payment/billing/payments/notifications", "application/json", bytes.NewReader(payload))
		if requestErr != nil {
			t.Fatal(requestErr)
		}
		var body ashrclone.JSONMap
		if decodeErr := json.NewDecoder(response.Body).Decode(&body); decodeErr != nil {
			response.Body.Close()
			t.Fatal(decodeErr)
		}
		response.Body.Close()
		if response.StatusCode != http.StatusForbidden {
			t.Fatalf("forged notification status=%d body=%#v", response.StatusCode, body)
		}
		errorBody, _ := body["error"].(map[string]any)
		if errorBody["code"] != "trusted_payment_verification_required" {
			t.Fatalf("unexpected rejection: %#v", body)
		}
	}
	order, err := payments.GetOrder(context.Background(), "tenant_payment", "project_payment", "merchant_payment", ashrclone.PaymentProviderWeChatPay, "order_payment")
	if err != nil || order.Result.Status != ashrclone.PaymentOrderStatusCreated || order.Result.ProviderStatus != "" {
		t.Fatalf("public attack changed order: %#v err=%v", order.Result, err)
	}
	notifications, err := payments.ListNotifications(context.Background(), "tenant_payment", "project_payment", "merchant_payment", ashrclone.PaymentProviderWeChatPay, 100)
	if err != nil || notifications.Result.Count != 0 {
		t.Fatalf("public attack persisted notification: %#v err=%v", notifications.Result, err)
	}
}

func TestGoSDKRuntimeDTOParitySmoke(t *testing.T) {
	service := ashrclone.NewMemoryService()
	input := ashrclone.AgentInputFromParts([]ashrclone.AgentInputPart{
		{Type: ashrclone.ModalityText, Text: "grade this workflow"},
		{Type: ashrclone.ModalityAudio, URL: "https://example.invalid/audio.wav", MIMEType: "audio/wav"},
		{Type: ashrclone.ModalityFile, Path: "fixtures/spec.pdf", MIMEType: "application/pdf"},
		{Type: ashrclone.ModalityImage, Path: "fixtures/image.png", MIMEType: "image/png"},
		{Type: ashrclone.ModalityVideo, URL: "https://example.invalid/video.mp4", MIMEType: "video/mp4"},
	}, ashrclone.JSONMap{"source": "go_integration"})
	boot, err := service.BootstrapProject("Tenant", "Project", ashrclone.Dataset{Name: "Dataset", Cases: []ashrclone.DatasetCase{{CaseID: "case_1", Input: input}}}, "tenant_go", "project_go")
	if err != nil {
		t.Fatal(err)
	}
	run, err := service.SubmitRun("tenant_go", "project_go", boot.Result.Dataset.DatasetID, "agent:go", "run_go", nil, ashrclone.IdempotencyOptions{Key: "idem_go"})
	if err != nil {
		t.Fatal(err)
	}
	if run.Result.Status != "queued" {
		t.Fatalf("status = %q", run.Result.Status)
	}
	payload, err := json.Marshal(boot)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"tenant_id", "project_id", "dataset_id", "schema_version", "audio", "file", "image", "video"} {
		if !strings.Contains(string(payload), want) {
			t.Fatalf("bootstrap payload missing %q: %s", want, payload)
		}
	}
}

func TestGoSDKWorkerJobControlPlaneLifecycleSmoke(t *testing.T) {
	service := ashrclone.NewMemoryService()
	boot, err := service.BootstrapProject("Tenant", "Workers", ashrclone.Dataset{Name: "Dataset"}, "tenant_go", "project_go")
	if err != nil {
		t.Fatal(err)
	}
	job, err := service.EnqueueWorkerJob("tenant_go", "project_go", "release_gate", "run_go", ashrclone.JSONMap{"gate": "candidate"}, ashrclone.EnqueueWorkerJobOptions{JobID: "job_go", MaxAttempts: 2, IdempotencyKey: "idem_worker"})
	if err != nil {
		t.Fatal(err)
	}
	if job.Result.SchemaVersion != ashrclone.ControlPlaneSchemaVersion || job.Result.TenantID != boot.Result.Tenant.TenantID || job.Result.PayloadSHA256 == "" || job.Result.RawPayloadIncluded {
		t.Fatalf("unexpected worker job: %#v", job.Result)
	}
	lease, err := service.LeaseWorkerJob("tenant_go", "project_go", "worker_go", ashrclone.LeaseWorkerJobOptions{JobType: "release_gate"})
	if err != nil {
		t.Fatal(err)
	}
	if !lease.Result.Leased || lease.Result.Job == nil || lease.Result.Job.JobID != "job_go" {
		t.Fatalf("unexpected lease: %#v", lease.Result)
	}
	completed, err := service.CompleteWorkerJob("tenant_go", "project_go", "job_go", "worker_go", ashrclone.JSONMap{"status": "ok"}, ashrclone.CompleteWorkerJobOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if completed.Result.Status != ashrclone.WorkerJobStatusCompleted || completed.Result.ResultSHA256 == "" {
		t.Fatalf("unexpected completion: %#v", completed.Result)
	}
}

func TestGoSDKRouteScopeDocsUsageQuotaLifecycleAudit(t *testing.T) {
	docs := ashrclone.GoRouteScopeDocs(ashrclone.GoRouteManifestEntries())
	if docs.SchemaVersion != "ashr.clone.go_route_scope_docs.v1" || !docs.PublicSafe || docs.RawPayloadsIncluded {
		t.Fatalf("unexpected route scope docs metadata: %#v", docs)
	}
	for _, want := range []string{"usage_quota", "run_lifecycle", "audit"} {
		if routeScopeGroupForIntegration(docs, want) == nil {
			t.Fatalf("missing route scope docs group %q: %#v", want, docs.RouteGroups)
		}
	}
	usage := routeScopeGroupForIntegration(docs, "usage_quota")
	if !containsStringForIntegration(usage.Routes, "GET /v1/projects/{project_id}/usage") || !containsStringForIntegration(usage.Routes, "GET /v1/projects/{project_id}/quota") || !containsStringForIntegration(usage.Scopes, ashrclone.ScopeUsageRead) {
		t.Fatalf("usage/quota route docs are not importable from integration module: %#v", usage)
	}
	metrics := map[string]bool{}
	for _, metric := range docs.PlanMetrics {
		metrics[metric.Metric] = true
	}
	for _, want := range []string{"graded_scenarios", "observations", "voice_minutes", "projects"} {
		if !metrics[want] {
			t.Fatalf("missing public plan metric %q: %#v", want, docs.PlanMetrics)
		}
	}
	developer := routeScopePlanForIntegration(docs, "Developer")
	startup := routeScopePlanForIntegration(docs, "Startup")
	if developer == nil || startup == nil {
		t.Fatalf("missing public plan limit references: %#v", docs.PlanLimits)
	}
	if routeScopeLimitForIntegration(developer, "graded_scenarios") != 5000 || routeScopeLimitForIntegration(startup, "voice_minutes") != 50000 {
		t.Fatalf("unexpected public plan limits: developer=%#v startup=%#v", developer.Limits, startup.Limits)
	}
	encoded, err := json.Marshal(docs)
	if err != nil {
		t.Fatal(err)
	}
	for _, secretish := range []string{"tenant_", "project_contract", "key_contract", "sk-"} {
		if strings.Contains(string(encoded), secretish) {
			t.Fatalf("route scope docs include fixture/secret-like value %q: %s", secretish, encoded)
		}
	}
}

func TestGoSDKHostedUploadParityAndMediaSafety(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.EscapedPath() != "/v1/projects/project_go/runs/run_go/upload" {
			t.Fatalf("unexpected request target %s %s", r.Method, r.URL.EscapedPath())
		}
		if r.Header.Get("Idempotency-Key") != "idem_upload" || r.Header.Get("X-Request-ID") != "req_upload" {
			t.Fatalf("missing idempotency/request headers: %#v", r.Header)
		}
		var body ashrclone.JSONMap
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body["tenant_id"] != "tenant_go" || body["upload_id"] != "upload_go" {
			t.Fatalf("unexpected upload body: %#v", body)
		}
		result, ok := body["result"].(map[string]any)
		if !ok || result["artifact_url"] != "https://example.invalid/artifact.json" {
			t.Fatalf("unexpected result envelope: %#v", body["result"])
		}
		_, _ = w.Write([]byte(`{"uploaded":true}`))
	}))
	defer server.Close()

	client := ashrclone.NewClient(ashrclone.WithBaseURL(server.URL))
	response, err := client.UploadRunHTTP(context.Background(), "tenant_go", "project_go", "run_go", ashrclone.JSONMap{"artifact_url": "https://example.invalid/artifact.json"}, ashrclone.UploadRunOptions{UploadID: "upload_go", IdempotencyKey: "idem_upload", RequestID: "req_upload"})
	if err != nil {
		t.Fatal(err)
	}
	if response.Operation != "upload_run" || response.Result["uploaded"] != true {
		t.Fatalf("unexpected hosted response: %#v", response)
	}

	_, err = client.UploadRunHTTP(context.Background(), "tenant_go", "project_go", "run_go", ashrclone.JSONMap{"data_url": "data:image/png;base64,iVBORw0KGgo="}, ashrclone.UploadRunOptions{IdempotencyKey: "idem_upload_2"})
	var mediaErr ashrclone.MediaSafetyError
	if !errors.As(err, &mediaErr) {
		t.Fatalf("expected media safety error, got %T %v", err, err)
	}
}

func routeScopeGroupForIntegration(docs ashrclone.RouteScopeDocs, name string) *ashrclone.RouteScopeDocGroup {
	for i := range docs.RouteGroups {
		if docs.RouteGroups[i].Name == name {
			return &docs.RouteGroups[i]
		}
	}
	return nil
}

func routeScopePlanForIntegration(docs ashrclone.RouteScopeDocs, name string) *ashrclone.RouteScopeDocPlan {
	for i := range docs.PlanLimits {
		if docs.PlanLimits[i].Plan == name {
			return &docs.PlanLimits[i]
		}
	}
	return nil
}

func routeScopeLimitForIntegration(plan *ashrclone.RouteScopeDocPlan, metric string) int {
	for _, item := range plan.Limits {
		if item.Metric == metric {
			return item.Limit
		}
	}
	return -1
}

func containsStringForIntegration(items []string, want string) bool {
	for _, item := range items {
		if item == want {
			return true
		}
	}
	return false
}
