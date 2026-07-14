package ashrclone

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type identityProofResolverFunc func(context.Context, TrustedIdentityProofRequest) (TrustedIdentityProof, error)

func (resolver identityProofResolverFunc) ResolveTrustedIdentityProof(
	ctx context.Context,
	request TrustedIdentityProofRequest,
) (TrustedIdentityProof, error) {
	return resolver(ctx, request)
}

func newIdentityLifecycleTestService(t *testing.T) (*IdentityLifecycleService, *UnifiedIdentityService, *time.Time) {
	t.Helper()
	identity, now := newIdentityTestService(t)
	lifecycle, err := NewIdentityLifecycleService(identity, IdentityLifecycleOptions{
		Now: func() time.Time { return *now }, Random: &identitySequenceReader{},
		ReceiptTTL: 2 * time.Minute, GitHubEnabled: true, GoogleEnabled: true,
		Environment: "test",
	})
	if err != nil {
		t.Fatal(err)
	}
	return lifecycle, identity, now
}

func issueLifecycleProof(t *testing.T, lifecycle *IdentityLifecycleService, proof TrustedIdentityProof) IdentityProofReceiptDTO {
	t.Helper()
	receipt, err := lifecycle.issueTrustedProofReceipt(proof)
	if err != nil {
		t.Fatalf("issue proof receipt: %v", err)
	}
	return receipt
}

func completionFor(receipt IdentityProofReceiptDTO) CompleteIdentityLifecycleRequest {
	return CompleteIdentityLifecycleRequest{
		ReceiptID: receipt.ReceiptID, Provider: receipt.Provider,
		TenantID: receipt.TenantID, ProjectID: receipt.ProjectID,
	}
}

func TestIdentityLifecycleRegistrationRequiresTrustedReceiptAndLoginCredential(t *testing.T) {
	lifecycle, identity, _ := newIdentityLifecycleTestService(t)
	if _, err := lifecycle.CompleteRegistration(CompleteIdentityLifecycleRequest{
		ReceiptID: "ipr_caller-controlled", Provider: IdentityProviderLocal,
	}); !errors.Is(err, ErrIdentityProofReceiptNotFound) {
		t.Fatalf("untrusted registration completion was accepted: %v", err)
	}
	accounts, credentials := identity.IdentityObjectCounts()
	if accounts != 0 || credentials != 0 {
		t.Fatalf("failed registration mutated identity: accounts=%d credentials=%d", accounts, credentials)
	}

	receipt := issueLifecycleProof(t, lifecycle, TrustedIdentityProof{
		Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
		Provider: IdentityProviderLocal, Identifier: "owner@example.cn",
		DisplayName: "Domestic Email Owner",
	})
	account, err := lifecycle.CompleteRegistration(completionFor(receipt))
	if err != nil {
		t.Fatal(err)
	}
	if account.CredentialCount != 1 || account.Credentials[0].Provider != IdentityProviderLocal ||
		!account.Credentials[0].CanLogin {
		t.Fatalf("registration did not create exactly one login credential: %#v", account)
	}
}

func TestIdentityLifecycleStartRejectsResolverScopeSubstitution(t *testing.T) {
	identity, _ := newIdentityTestService(t)
	for name, mutate := range map[string]func(*TrustedIdentityProof){
		"operation": func(proof *TrustedIdentityProof) { proof.Operation = IdentityOperationLogin },
		"provider":  func(proof *TrustedIdentityProof) { proof.Provider = IdentityProviderGoogle },
		"tenant":    func(proof *TrustedIdentityProof) { proof.TenantID = "tenant-b" },
		"project":   func(proof *TrustedIdentityProof) { proof.ProjectID = "project-b" },
	} {
		t.Run(name, func(t *testing.T) {
			resolver := identityProofResolverFunc(func(_ context.Context, request TrustedIdentityProofRequest) (TrustedIdentityProof, error) {
				proof := TrustedIdentityProof{
					Operation: request.Operation, Kind: IdentityCredentialEmail,
					Provider: request.Provider, Identifier: "owner@example.cn",
					TenantID: request.TenantID, ProjectID: request.ProjectID,
				}
				mutate(&proof)
				return proof, nil
			})
			lifecycle, err := NewIdentityLifecycleService(identity, IdentityLifecycleOptions{
				ProofResolver: resolver,
			})
			if err != nil {
				t.Fatal(err)
			}
			_, err = lifecycle.Start(context.Background(), TrustedIdentityProofRequest{
				Operation: IdentityOperationRegistration, Provider: IdentityProviderLocal,
				TenantID: "tenant-a", ProjectID: "project-a",
			})
			var domain IdentityDomainError
			if !errors.As(err, &domain) || domain.Code != "trusted_proof_scope_mismatch" {
				t.Fatalf("resolver scope substitution returned %v", err)
			}
			if lifecycle.developmentReceiptCount() != 0 {
				t.Fatal("scope-substituted resolver proof minted a receipt")
			}
		})
	}
}

func TestIdentityLifecycleOAuthFirstRegistrationKeepsPasswordAbsent(t *testing.T) {
	lifecycle, _, _ := newIdentityLifecycleTestService(t)
	receipt := issueLifecycleProof(t, lifecycle, TrustedIdentityProof{
		Operation: IdentityOperationRegistration, Kind: IdentityCredentialOAuth,
		Provider: IdentityProviderGoogle, Identifier: "google-subject",
		VerifiedEmail: "owner@example.com", DisplayName: "OAuth Owner",
	})
	account, err := lifecycle.CompleteRegistration(completionFor(receipt))
	if err != nil {
		t.Fatal(err)
	}
	if account.SecurityPosture.Password.Status != "absent" ||
		!account.SecurityPosture.PrimaryEmail.Present ||
		account.SecurityPosture.PrimaryEmail.Source != IdentityProviderGoogle {
		t.Fatalf("unexpected oauth-first security posture: %#v", account.SecurityPosture)
	}
}

func TestIdentityLifecycleUnknownLoginHasNoMutation(t *testing.T) {
	lifecycle, identity, _ := newIdentityLifecycleTestService(t)
	beforeAccounts, beforeCredentials := identity.IdentityObjectCounts()
	receipt := issueLifecycleProof(t, lifecycle, TrustedIdentityProof{
		Operation: IdentityOperationLogin, Kind: IdentityCredentialEmail,
		Provider: IdentityProviderLocal, Identifier: "unknown@example.cn",
	})
	if _, err := lifecycle.CompleteLogin(completionFor(receipt)); !errors.Is(err, ErrIdentityCredentialNotFound) {
		t.Fatalf("unknown login returned %v", err)
	}
	afterAccounts, afterCredentials := identity.IdentityObjectCounts()
	if beforeAccounts != afterAccounts || beforeCredentials != afterCredentials {
		t.Fatalf("unknown login mutated identity: before=%d/%d after=%d/%d",
			beforeAccounts, beforeCredentials, afterAccounts, afterCredentials)
	}
}

func TestIdentityLifecycleReceiptScopeMismatchDoesNotConsumeOrMutate(t *testing.T) {
	lifecycle, identity, _ := newIdentityLifecycleTestService(t)
	receipt := issueLifecycleProof(t, lifecycle, TrustedIdentityProof{
		Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
		Provider: IdentityProviderLocal, Identifier: "scoped@example.cn",
		TenantID: "tenant-a", ProjectID: "project-a",
	})
	for _, mismatch := range []CompleteIdentityLifecycleRequest{
		{ReceiptID: receipt.ReceiptID, Provider: IdentityProviderGoogle, TenantID: "tenant-a", ProjectID: "project-a"},
		{ReceiptID: receipt.ReceiptID, Provider: IdentityProviderLocal, TenantID: "tenant-b", ProjectID: "project-a"},
		{ReceiptID: receipt.ReceiptID, Provider: IdentityProviderLocal, TenantID: "tenant-a", ProjectID: "project-b"},
	} {
		if _, err := lifecycle.CompleteRegistration(mismatch); !errors.Is(err, ErrIdentityProofScopeMismatch) {
			t.Fatalf("scope mismatch returned %v", err)
		}
	}
	accounts, credentials := identity.IdentityObjectCounts()
	if accounts != 0 || credentials != 0 {
		t.Fatalf("scope mismatch mutated identity: %d/%d", accounts, credentials)
	}
	if _, err := lifecycle.CompleteRegistration(completionFor(receipt)); err != nil {
		t.Fatalf("scope mismatch consumed valid receipt: %v", err)
	}
}

func TestIdentityLifecycleReceiptExpiresAndReplaysFail(t *testing.T) {
	lifecycle, _, now := newIdentityLifecycleTestService(t)
	expired := issueLifecycleProof(t, lifecycle, TrustedIdentityProof{
		Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
		Provider: IdentityProviderLocal, Identifier: "expired@example.cn",
	})
	*now = now.Add(3 * time.Minute)
	if _, err := lifecycle.CompleteRegistration(completionFor(expired)); !errors.Is(err, ErrIdentityProofReceiptExpired) {
		t.Fatalf("expired receipt returned %v", err)
	}

	*now = now.Add(-3 * time.Minute)
	receipt := issueLifecycleProof(t, lifecycle, TrustedIdentityProof{
		Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
		Provider: IdentityProviderLocal, Identifier: "once@example.cn",
	})
	if _, err := lifecycle.CompleteRegistration(completionFor(receipt)); err != nil {
		t.Fatal(err)
	}
	if _, err := lifecycle.CompleteRegistration(completionFor(receipt)); !errors.Is(err, ErrIdentityProofReceiptConsumed) {
		t.Fatalf("replayed receipt returned %v", err)
	}
}

func TestIdentityLifecycleConcurrentReceiptConsumptionHasOneWinner(t *testing.T) {
	lifecycle, identity, _ := newIdentityLifecycleTestService(t)
	receipt := issueLifecycleProof(t, lifecycle, TrustedIdentityProof{
		Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
		Provider: IdentityProviderLocal, Identifier: "race@example.cn",
	})
	var successes atomic.Int32
	var consumed atomic.Int32
	var wait sync.WaitGroup
	for index := 0; index < 32; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			_, err := lifecycle.CompleteRegistration(completionFor(receipt))
			switch {
			case err == nil:
				successes.Add(1)
			case errors.Is(err, ErrIdentityProofReceiptConsumed):
				consumed.Add(1)
			default:
				t.Errorf("unexpected concurrent completion error: %v", err)
			}
		}()
	}
	wait.Wait()
	accounts, credentials := identity.IdentityObjectCounts()
	if successes.Load() != 1 || consumed.Load() != 31 || accounts != 1 || credentials != 1 {
		t.Fatalf("receipt race was not atomic: success=%d consumed=%d identity=%d/%d",
			successes.Load(), consumed.Load(), accounts, credentials)
	}
}

type durableReceiptStoreStub struct{}

func (durableReceiptStoreStub) Issue(context.Context, IdentityProofReceiptDTO, TrustedIdentityProof) error {
	return nil
}
func (durableReceiptStoreStub) Consume(context.Context, CompleteIdentityLifecycleRequest, IdentityLifecycleOperation, time.Time) (TrustedIdentityProof, error) {
	return TrustedIdentityProof{}, nil
}
func (durableReceiptStoreStub) ProductionDurable() bool { return true }

type coordinatorOnlyIdentityLifecycleStub struct{}

func (coordinatorOnlyIdentityLifecycleStub) CompleteRegistration(
	context.Context,
	CompleteIdentityLifecycleRequest,
	time.Time,
) (IdentityAccountDTO, error) {
	return IdentityAccountDTO{}, nil
}

func (coordinatorOnlyIdentityLifecycleStub) CompleteLogin(
	context.Context,
	CompleteIdentityLifecycleRequest,
	time.Time,
) (IdentityAuthenticationDTO, error) {
	return IdentityAuthenticationDTO{}, nil
}

func TestIdentityLifecycleAllowsAtomicCoordinatorWithoutMemoryIdentity(t *testing.T) {
	service, err := NewIdentityLifecycleService(nil, IdentityLifecycleOptions{
		Coordinator: coordinatorOnlyIdentityLifecycleStub{},
	})
	if err != nil {
		t.Fatal(err)
	}
	if service.identity != nil || service.coord == nil {
		t.Fatalf("coordinator-only lifecycle was not configured: %#v", service)
	}
}

func TestIdentityLifecycleRejectsMissingIdentityAndCoordinator(t *testing.T) {
	if _, err := NewIdentityLifecycleService(nil, IdentityLifecycleOptions{}); err == nil ||
		!strings.Contains(err.Error(), "transaction coordinator") {
		t.Fatalf("missing identity authority did not fail closed: %v", err)
	}
}

func TestIdentityLifecycleRejectsDurableReceiptWithoutAtomicCoordinator(t *testing.T) {
	identity, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{
		FingerprintKey: []byte("01234567890123456789012345678901"),
	})
	if err != nil {
		t.Fatal(err)
	}
	_, err = NewIdentityLifecycleService(identity, IdentityLifecycleOptions{
		ReceiptStore: durableReceiptStoreStub{},
	})
	if err == nil || !strings.Contains(err.Error(), "atomic transaction coordinator") {
		t.Fatalf("durable receipt store was accepted without atomic coordinator: %v", err)
	}
}

func TestIdentityLifecycleDomesticProvidersFailClosed(t *testing.T) {
	lifecycle, _, _ := newIdentityLifecycleTestService(t)
	for _, provider := range []IdentityProvider{IdentityProviderWeChat, IdentityProviderQQ, IdentityProviderAlipay} {
		_, err := lifecycle.issueTrustedProofReceipt(TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialOAuth,
			Provider: provider, Identifier: "provider-subject",
		})
		var domain IdentityDomainError
		if !errors.As(err, &domain) || domain.Code != "identity_provider_unavailable" {
			t.Fatalf("%s did not fail closed: %v", provider, err)
		}
	}
	capabilities := lifecycle.ProviderCapabilities()
	for _, provider := range []IdentityProvider{IdentityProviderLocal, IdentityProviderGitHub, IdentityProviderGoogle} {
		for _, capability := range capabilities {
			if capability.Provider == provider && capability.LinkingStatus != "proposed" {
				t.Fatalf("%s linking must remain proposed until routes are active: %#v", provider, capability)
			}
		}
	}
	for _, provider := range []IdentityProvider{IdentityProviderWeChat, IdentityProviderQQ, IdentityProviderAlipay} {
		found := false
		for _, capability := range capabilities {
			if capability.Provider == provider {
				found = true
				if capability.Available || capability.Enabled || !capability.RequiresBusinessQualification ||
					capability.QualificationStatus != "required" || capability.LinkingStatus != "unavailable" {
					t.Fatalf("unsafe domestic provider capability: %#v", capability)
				}
			}
		}
		if !found {
			t.Fatalf("missing capability for %s", provider)
		}
	}
}

func TestIdentityLifecycleHTTPRoutesAndAntiEnumeration(t *testing.T) {
	lifecycle, identity, _ := newIdentityLifecycleTestService(t)
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		UnifiedIdentity: identity, IdentityLifecycle: lifecycle,
	})

	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/v1/identity/providers", nil))
	if response.Code != http.StatusOK ||
		!strings.Contains(response.Body.String(), `"schema_version":"ashr.clone.a3_identity.providers.v1"`) ||
		!strings.Contains(response.Body.String(), `"provider":"email"`) ||
		!strings.Contains(response.Body.String(), `"preferred":true`) ||
		!strings.Contains(response.Body.String(), `"code_capability":"implemented"`) ||
		!strings.Contains(response.Body.String(), `"deployment_readiness":"ready"`) ||
		!strings.Contains(response.Body.String(), `"requires_business_qualification":true`) ||
		!strings.Contains(response.Body.String(), `"linking_status":"proposed"`) {
		t.Fatalf("provider capability response: status=%d body=%s", response.Code, response.Body.String())
	}

	loginReceipt := issueLifecycleProof(t, lifecycle, TrustedIdentityProof{
		Operation: IdentityOperationLogin, Kind: IdentityCredentialEmail,
		Provider: IdentityProviderLocal, Identifier: "missing@example.cn",
	})
	body, _ := json.Marshal(map[string]any{
		"receipt_id": loginReceipt.ReceiptID, "provider": "local",
	})
	response = httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/v1/identity/login/complete", bytes.NewReader(body)))
	if response.Code != http.StatusUnauthorized ||
		!strings.Contains(response.Body.String(), `"code":"authentication_failed"`) ||
		!strings.Contains(response.Body.String(), `"anti_enumeration":true`) ||
		strings.Contains(response.Body.String(), "not found") {
		t.Fatalf("login anti-enumeration response: status=%d body=%s", response.Code, response.Body.String())
	}

	startBody := strings.NewReader(`{"kind":"email","provider":"local","email":"owner@example.cn"}`)
	response = httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodPost, "/v1/identity/registration/start", startBody))
	if response.Code != http.StatusBadRequest ||
		(!strings.Contains(response.Body.String(), `"trusted_proof_provider_unavailable"`) &&
			!strings.Contains(response.Body.String(), `"provider_unavailable"`)) {
		t.Fatalf("untrusted registration start did not fail closed: status=%d body=%s", response.Code, response.Body.String())
	}

	for _, route := range []string{
		"/v1/identity/registration/start",
		"/v1/identity/registration/complete",
		"/v1/identity/login/start",
		"/v1/identity/login/complete",
	} {
		for _, field := range forbiddenPublicIdentityProofFields {
			body := strings.NewReader(`{"provider":"local","` + field + `":"caller-controlled"}`)
			response = httptest.NewRecorder()
			handler.ServeHTTP(response, httptest.NewRequest(http.MethodPost, route, body))
			if response.Code != http.StatusBadRequest ||
				!strings.Contains(response.Body.String(), `"caller_verified_proof_rejected"`) {
				t.Fatalf("%s accepted forbidden field %s: status=%d body=%s",
					route, field, response.Code, response.Body.String())
			}
		}
	}
}

type failingIdentityLifecycleCoordinator struct {
	loginErr error
}

func (coordinator failingIdentityLifecycleCoordinator) CompleteRegistration(
	context.Context,
	CompleteIdentityLifecycleRequest,
	time.Time,
) (IdentityAccountDTO, error) {
	return IdentityAccountDTO{}, errors.New("registration coordinator unavailable")
}

func (coordinator failingIdentityLifecycleCoordinator) CompleteLogin(
	context.Context,
	CompleteIdentityLifecycleRequest,
	time.Time,
) (IdentityAuthenticationDTO, error) {
	return IdentityAuthenticationDTO{}, coordinator.loginErr
}

func TestIdentityLifecycleHTTPSeparatesCredentialFailuresFromOperationalFaults(t *testing.T) {
	testCases := []struct {
		name          string
		err           error
		wantStatus    int
		wantCode      string
		wantRetryable bool
	}{
		{
			name: "unknown credential remains anti-enumeration authentication failure",
			err:  ErrIdentityCredentialNotFound, wantStatus: http.StatusUnauthorized,
			wantCode: "authentication_failed", wantRetryable: false,
		},
		{
			name:       "database timeout becomes retryable public-safe service failure",
			err:        errors.New("dial tcp postgres.internal:5432: i/o timeout"),
			wantStatus: http.StatusServiceUnavailable,
			wantCode:   "provider_unavailable", wantRetryable: true,
		},
	}
	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			identity, _ := newIdentityTestService(t)
			lifecycle, err := NewIdentityLifecycleService(identity, IdentityLifecycleOptions{
				Coordinator: failingIdentityLifecycleCoordinator{loginErr: testCase.err},
			})
			if err != nil {
				t.Fatalf("new lifecycle service: %v", err)
			}
			handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
				UnifiedIdentity: identity, IdentityLifecycle: lifecycle,
			})
			response := httptest.NewRecorder()
			body := strings.NewReader(`{"receipt_id":"ipr_public_opaque","provider":"email"}`)
			handler.ServeHTTP(
				response,
				httptest.NewRequest(http.MethodPost, "/v1/identity/login/complete", body),
			)
			if response.Code != testCase.wantStatus ||
				!strings.Contains(response.Body.String(), `"code":"`+testCase.wantCode+`"`) ||
				!strings.Contains(response.Body.String(), fmt.Sprintf(`"retryable":%t`, testCase.wantRetryable)) ||
				!strings.Contains(response.Body.String(), `"anti_enumeration":true`) ||
				strings.Contains(response.Body.String(), "postgres.internal") ||
				strings.Contains(response.Body.String(), "i/o timeout") {
				t.Fatalf("unexpected public error: status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}
}

func TestGoRouteManifestIncludesOnlyImplementedIdentityLifecycleRoutes(t *testing.T) {
	expected := map[string]bool{
		"GET /v1/identity/providers":              false,
		"POST /v1/identity/registration/start":    false,
		"POST /v1/identity/registration/complete": false,
		"POST /v1/identity/login/start":           false,
		"POST /v1/identity/login/complete":        false,
	}
	for _, entry := range GoRouteManifestEntries() {
		if _, ok := expected[entry.Route]; ok {
			expected[entry.Route] = true
		}
		if strings.Contains(entry.Route, "/v1/identity/") &&
			(strings.Contains(entry.Route, "/link") || strings.Contains(entry.Route, "/password") ||
				strings.Contains(entry.Route, "/two-factor")) {
			t.Fatalf("manifest advertises unimplemented identity route %s", entry.Route)
		}
	}
	for route, found := range expected {
		if !found {
			t.Errorf("manifest omitted implemented route %s", route)
		}
	}
}

func TestIdentityLifecycleReceiptDigestsPreferActiveKey(t *testing.T) {
	activeKey := []byte("active-lifecycle-key-012345678901234")
	previousKey := []byte("previous-lifecycle-key-012345678901")
	ring, err := newIdentityLifecycleKeyring(
		"z-active",
		activeKey,
		[]IdentityLifecycleEncryptionKey{{Version: "a-previous", Key: previousKey}},
	)
	if err != nil {
		t.Fatal(err)
	}
	defer ring.close()

	raw := "credential:google:provider-subject"
	digests := ring.receiptDigests(raw)
	if len(digests) != 2 {
		t.Fatalf("unexpected digest count: %d", len(digests))
	}
	if digests[0] != ring.receiptDigest(raw) {
		t.Fatal("active lifecycle key digest was not first")
	}

	previousOnly, err := newIdentityLifecycleKeyring("a-previous", previousKey, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer previousOnly.close()
	if digests[1] != previousOnly.receiptDigest(raw) {
		t.Fatal("previous lifecycle key digest was not retained for lookup")
	}
}
