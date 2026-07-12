package ashrclone

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

func compileA3IdentitySchema(t *testing.T, name string) *jsonschema.Schema {
	t.Helper()
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve identity schema test source")
	}
	path := filepath.Join(filepath.Dir(source), "..", "..", "..", "docs", "a1", "schemas", name)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", name, err)
	}
	var document any
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode %s: %v", name, err)
	}
	compiler := jsonschema.NewCompiler()
	compiler.AssertFormat()
	const resource = "https://ashr.local/schema-under-test.json"
	if err := compiler.AddResource(resource, document); err != nil {
		t.Fatalf("add %s: %v", name, err)
	}
	schema, err := compiler.Compile(resource)
	if err != nil {
		t.Fatalf("compile %s: %v", name, err)
	}
	return schema
}

func serveIdentityJSON(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body map[string]any,
) (int, any) {
	t.Helper()
	var encoded []byte
	var err error
	if body != nil {
		encoded, err = json.Marshal(body)
		if err != nil {
			t.Fatal(err)
		}
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(method, path, bytes.NewReader(encoded)))
	var document any
	if err := json.Unmarshal(response.Body.Bytes(), &document); err != nil {
		t.Fatalf("%s %s returned invalid JSON: %s", method, path, response.Body.String())
	}
	return response.Code, document
}

func TestA3IdentityLifecycleLiveResponsesValidateAgainstSchemas(t *testing.T) {
	responseSchema := compileA3IdentitySchema(t, "a3_identity_registration_login_contract.schema.json")
	providerSchema := compileA3IdentitySchema(t, "a3_identity_provider_capabilities.schema.json")

	identity, now := newIdentityTestService(t)
	resolver := identityProofResolverFunc(func(_ context.Context, request TrustedIdentityProofRequest) (TrustedIdentityProof, error) {
		email := request.Inputs["email"]
		if email == "" {
			email = "schema-owner@example.cn"
		}
		return TrustedIdentityProof{
			Operation: request.Operation, Kind: IdentityCredentialEmail,
			Provider: request.Provider, Identifier: email, VerifiedEmail: email,
			TenantID: request.TenantID, ProjectID: request.ProjectID,
		}, nil
	})
	lifecycle, err := NewIdentityLifecycleService(identity, IdentityLifecycleOptions{
		Now: func() time.Time { return *now }, Random: &identitySequenceReader{},
		ReceiptTTL: 2 * time.Minute, ProofResolver: resolver,
		GitHubEnabled: true, GoogleEnabled: true, Environment: "schema-test",
	})
	if err != nil {
		t.Fatal(err)
	}
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		UnifiedIdentity: identity, IdentityLifecycle: lifecycle,
	})

	status, providers := serveIdentityJSON(t, handler, http.MethodGet, "/v1/identity/providers", nil)
	if status != http.StatusOK {
		t.Fatalf("provider status=%d", status)
	}
	if err := providerSchema.Validate(providers); err != nil {
		t.Fatalf("provider response violates A3 schema: %v", err)
	}

	scope := map[string]any{
		"provider": "email", "email": "schema-owner@example.cn",
		"tenant_id": "tenant-schema", "project_id": "project-schema",
	}
	status, registerStart := serveIdentityJSON(
		t, handler, http.MethodPost, "/v1/identity/registration/start", scope,
	)
	if status != http.StatusCreated {
		t.Fatalf("registration start status=%d document=%v", status, registerStart)
	}
	if err := responseSchema.Validate(registerStart); err != nil {
		t.Fatalf("registration start violates A3 schema: %v", err)
	}
	registerReceipt := registerStart.(map[string]any)["receipt_id"]
	registerCompleteBody := map[string]any{
		"provider": "email", "receipt_id": registerReceipt,
		"tenant_id": "tenant-schema", "project_id": "project-schema",
	}
	status, registerComplete := serveIdentityJSON(
		t, handler, http.MethodPost, "/v1/identity/registration/complete", registerCompleteBody,
	)
	if status != http.StatusCreated {
		t.Fatalf("registration complete status=%d document=%v", status, registerComplete)
	}
	if err := responseSchema.Validate(registerComplete); err != nil {
		t.Fatalf("registration complete violates A3 schema: %v", err)
	}

	status, loginStart := serveIdentityJSON(t, handler, http.MethodPost, "/v1/identity/login/start", scope)
	if status != http.StatusCreated {
		t.Fatalf("login start status=%d document=%v", status, loginStart)
	}
	if err := responseSchema.Validate(loginStart); err != nil {
		t.Fatalf("login start violates A3 schema: %v", err)
	}
	loginReceipt := loginStart.(map[string]any)["receipt_id"]
	loginCompleteBody := map[string]any{
		"provider": "email", "receipt_id": loginReceipt,
		"tenant_id": "tenant-schema", "project_id": "project-schema",
	}
	status, loginComplete := serveIdentityJSON(
		t, handler, http.MethodPost, "/v1/identity/login/complete", loginCompleteBody,
	)
	if status != http.StatusOK {
		t.Fatalf("login complete status=%d document=%v", status, loginComplete)
	}
	if err := responseSchema.Validate(loginComplete); err != nil {
		t.Fatalf("login complete violates A3 schema: %v", err)
	}

	status, loginFailure := serveIdentityJSON(t, handler, http.MethodPost, "/v1/identity/login/complete", map[string]any{
		"provider": "email", "receipt_id": "ipr_unknown",
		"tenant_id": "tenant-schema", "project_id": "project-schema",
	})
	if status != http.StatusUnauthorized {
		t.Fatalf("login failure status=%d document=%v", status, loginFailure)
	}
	if err := responseSchema.Validate(loginFailure); err != nil {
		t.Fatalf("login failure violates A3 schema: %v", err)
	}
}
