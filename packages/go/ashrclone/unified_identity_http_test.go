package ashrclone

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type identityHTTPTestSessionResolver struct {
	session IdentityHTTPSession
	err     error
}

func (resolver identityHTTPTestSessionResolver) ResolveIdentityHTTPSession(context.Context, *http.Request) (IdentityHTTPSession, error) {
	return resolver.session, resolver.err
}

func TestUnifiedIdentityHTTPReadBoundaryUsesTrustedAccount(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "private-github-subject")
	membership, err := service.AddMembership(account.AccountID, IdentityMembershipRequest{
		TenantID: "tenant", ProjectID: "project", Role: "owner", ActorID: account.AccountID,
	})
	if err != nil {
		t.Fatalf("add membership: %v", err)
	}
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		UnifiedIdentity: service,
		IdentitySessions: identityHTTPTestSessionResolver{session: IdentityHTTPSession{
			AccountID: account.AccountID, ActorID: account.AccountID, SessionID: "session",
		}},
	})

	for _, suffix := range []string{"", "/credentials", "/memberships"} {
		request := httptest.NewRequest(http.MethodGet, "/v1/accounts/"+account.AccountID+suffix, nil)
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusOK {
			t.Fatalf("GET %s: status=%d body=%s", suffix, response.Code, response.Body.String())
		}
		if response.Header().Get("Cache-Control") != "no-store" ||
			response.Header().Get("Pragma") != "no-cache" ||
			response.Header().Get("X-Content-Type-Options") != "nosniff" {
			t.Fatalf("GET %s omitted identity response security headers: %#v", suffix, response.Header())
		}
		assertUnifiedIdentityPublicPayload(t, json.RawMessage(response.Body.Bytes()), "private-github-subject")
	}

	request := httptest.NewRequest(http.MethodGet, "/v1/accounts/"+account.AccountID+"/memberships", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if !strings.Contains(response.Body.String(), membership.MembershipID) {
		t.Fatalf("membership response omitted membership: %s", response.Body.String())
	}
}

func TestUnifiedIdentityHTTPTrustedSessionIgnoresCallerIdentityMaterial(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "trusted-subject")
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		UnifiedIdentity: service,
		IdentitySessions: identityHTTPTestSessionResolver{session: IdentityHTTPSession{
			AccountID: account.AccountID, ActorID: account.AccountID, SessionID: "trusted-session",
		}},
	})

	request := httptest.NewRequest(
		http.MethodGet,
		"/v1/accounts/"+account.AccountID+"/credentials?account_id=attacker&session_id=attacker",
		nil,
	)
	request.Header.Set("X-Ashr-Account-ID", "attacker")
	request.Header.Set("X-Ashr-Session-ID", "attacker")
	request.Header.Set("X-Ashr-Actor-ID", "attacker")
	request.AddCookie(&http.Cookie{Name: "account_id", Value: "attacker"})
	request.AddCookie(&http.Cookie{Name: "session_id", Value: "attacker"})
	request.Header.Set("Authorization", "Bearer caller-controlled-material")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("caller identity material influenced trusted session: status=%d body=%s", response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), account.AccountID) ||
		strings.Contains(response.Body.String(), "attacker") ||
		strings.Contains(response.Body.String(), "caller-controlled-material") {
		t.Fatalf("identity response trusted or reflected caller identity material: %s", response.Body.String())
	}
}

func TestUnifiedIdentityHTTPReadBoundaryRejectsCrossAccountAssertion(t *testing.T) {
	service, _ := newIdentityTestService(t)
	owner := createIdentityTestAccount(t, service, IdentityProviderGitHub, "owner-subject")
	other := createIdentityTestAccount(t, service, IdentityProviderGoogle, "other-subject")
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		UnifiedIdentity: service,
		IdentitySessions: identityHTTPTestSessionResolver{session: IdentityHTTPSession{
			AccountID: owner.AccountID, ActorID: owner.AccountID, SessionID: "session",
		}},
	})

	request := httptest.NewRequest(http.MethodGet, "/v1/accounts/"+other.AccountID+"/credentials", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusForbidden || !strings.Contains(response.Body.String(), `"account_mismatch"`) {
		t.Fatalf("cross-account assertion was not rejected: status=%d body=%s", response.Code, response.Body.String())
	}
	if strings.Contains(response.Body.String(), "other-subject") {
		t.Fatalf("cross-account response leaked credential material: %s", response.Body.String())
	}
}

func TestUnifiedIdentityHTTPBoundaryRequiresTrustedSession(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "subject")
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{UnifiedIdentity: service})

	request := httptest.NewRequest(http.MethodGet, "/v1/accounts/"+account.AccountID, nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusUnauthorized || !strings.Contains(response.Body.String(), `"identity_session_required"`) {
		t.Fatalf("missing session resolver did not fail closed: status=%d body=%s", response.Code, response.Body.String())
	}
}

func TestLocalhostDevIdentityHTTPSessionResolverRequiresDirectLoopbackAndChecksRevocation(t *testing.T) {
	resolver := LocalhostDevIdentityHTTPSessionResolver{
		Enabled: true, AccountID: "account", ActorID: "actor", SessionID: "session",
		Revoked: func(_ context.Context, sessionID string) (bool, error) {
			if sessionID != "session" {
				t.Fatalf("revocation check used unexpected session: %q", sessionID)
			}
			return true, nil
		},
	}

	request := httptest.NewRequest(http.MethodGet, "http://localhost:8787/v1/accounts/account", nil)
	request.RemoteAddr = "127.0.0.1:4242"
	session, err := resolver.ResolveIdentityHTTPSession(context.Background(), request)
	if err != nil {
		t.Fatalf("resolve direct loopback session: %v", err)
	}
	if !session.Revoked || session.AccountID != "account" || session.ActorID != "actor" || session.SessionID != "session" {
		t.Fatalf("unexpected trusted localhost session: %#v", session)
	}

	for _, mutate := range []func(*http.Request){
		func(req *http.Request) { req.RemoteAddr = "203.0.113.7:4242" },
		func(req *http.Request) { req.Header.Set("Forwarded", "for=203.0.113.7") },
		func(req *http.Request) { req.Header.Set("X-Forwarded-For", "203.0.113.7") },
		func(req *http.Request) { req.Header.Set("X-Real-IP", "203.0.113.7") },
	} {
		untrusted := httptest.NewRequest(http.MethodGet, "http://localhost:8787/v1/accounts/account", nil)
		untrusted.RemoteAddr = "127.0.0.1:4242"
		mutate(untrusted)
		if _, err := resolver.ResolveIdentityHTTPSession(context.Background(), untrusted); err == nil {
			t.Fatalf("localhost resolver accepted proxied or non-loopback request: %#v", untrusted)
		}
	}
}

func TestUnifiedIdentityHTTPBoundaryRejectsRevokedOrIncompleteTrustedSession(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "subject")

	for _, test := range []struct {
		name    string
		session IdentityHTTPSession
	}{
		{name: "revoked", session: IdentityHTTPSession{AccountID: account.AccountID, ActorID: "actor", SessionID: "session", Revoked: true}},
		{name: "missing account", session: IdentityHTTPSession{ActorID: "actor", SessionID: "session"}},
		{name: "missing actor", session: IdentityHTTPSession{AccountID: account.AccountID, SessionID: "session"}},
		{name: "missing session", session: IdentityHTTPSession{AccountID: account.AccountID, ActorID: "actor"}},
	} {
		t.Run(test.name, func(t *testing.T) {
			handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
				UnifiedIdentity:  service,
				IdentitySessions: identityHTTPTestSessionResolver{session: test.session},
			})
			request := httptest.NewRequest(http.MethodGet, "/v1/accounts/"+account.AccountID, nil)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != http.StatusUnauthorized ||
				!strings.Contains(response.Body.String(), `"identity_session_invalid"`) {
				t.Fatalf("invalid trusted session did not fail closed: status=%d body=%s", response.Code, response.Body.String())
			}
		})
	}
}

func TestUnifiedIdentityHTTPMutationsFailClosedWithoutVerifiedAssertion(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "subject")
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		UnifiedIdentity: service,
		IdentitySessions: identityHTTPTestSessionResolver{session: IdentityHTTPSession{
			AccountID: account.AccountID, ActorID: account.AccountID, SessionID: "session",
		}},
	})

	targets := []string{
		"/v1/accounts/" + account.AccountID + "/credentials/google/link",
		"/v1/accounts/" + account.AccountID + "/credentials/" + account.Credentials[0].CredentialID + "/unlink",
	}
	for _, target := range targets {
		request := httptest.NewRequest(http.MethodPost, target, strings.NewReader(`{"identifier":"untrusted"}`))
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != http.StatusMethodNotAllowed ||
			!strings.Contains(response.Body.String(), `"identity_mutation_requires_verified_assertion"`) {
			t.Fatalf("mutation did not fail closed for %s: status=%d body=%s", target, response.Code, response.Body.String())
		}
	}
}

func TestUnifiedIdentityHTTPContractLinksGitHubAndGoogleToOneAccount(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "github-private-subject")

	google, err := service.LinkCredential(account.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{
			Kind:       IdentityCredentialOAuth,
			Provider:   IdentityProviderGoogle,
			Identifier: "google-private-subject",
			Verified:   true,
		},
		ActorID: account.AccountID,
	})
	if err != nil {
		t.Fatalf("link Google credential: %v", err)
	}

	updated, err := service.GetAccount(account.AccountID)
	if err != nil {
		t.Fatalf("get unified account: %v", err)
	}
	if updated.CredentialCount != 2 || google.Provider != IdentityProviderGoogle {
		t.Fatalf("expected one account with GitHub and Google credentials, got %#v", updated)
	}
	providers := make(map[IdentityProvider]bool, len(updated.Credentials))
	for _, credential := range updated.Credentials {
		providers[credential.Provider] = credential.Verified && credential.CanLogin
	}
	if !providers[IdentityProviderGitHub] || !providers[IdentityProviderGoogle] {
		t.Fatalf("unified account omitted a verified provider: %#v", providers)
	}
	assertUnifiedIdentityPublicPayload(t, updated,
		"github-private-subject",
		"google-private-subject",
	)

	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		UnifiedIdentity: service,
		IdentitySessions: identityHTTPTestSessionResolver{session: IdentityHTTPSession{
			AccountID: account.AccountID, ActorID: account.AccountID, SessionID: "session",
		}},
	})
	request := httptest.NewRequest(http.MethodGet, "/v1/accounts/"+account.AccountID+"/credentials", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("enumerate unified credentials: status=%d body=%s", response.Code, response.Body.String())
	}
	var payload struct {
		AccountID   string                         `json:"account_id"`
		Credentials []publicIdentityCredentialView `json:"credentials"`
		Count       int                            `json:"count"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode credential enumeration: %v", err)
	}
	if payload.AccountID != account.AccountID || payload.Count != 2 || len(payload.Credentials) != 2 {
		t.Fatalf("unexpected unified credential enumeration: %#v", payload)
	}
	httpProviders := map[IdentityProvider]bool{}
	for _, credential := range payload.Credentials {
		httpProviders[credential.Provider] = credential.Verified && credential.CanLogin
	}
	if !httpProviders[IdentityProviderGitHub] || !httpProviders[IdentityProviderGoogle] {
		t.Fatalf("HTTP enumeration omitted GitHub or Google credential: %#v", payload.Credentials)
	}
	assertUnifiedIdentityPublicPayload(t, json.RawMessage(response.Body.Bytes()),
		"github-private-subject",
		"google-private-subject",
	)
}

func TestUnifiedIdentityHTTPContractRejectsCrossAccountCredentialClaim(t *testing.T) {
	service, _ := newIdentityTestService(t)
	owner := createIdentityTestAccount(t, service, IdentityProviderGitHub, "owner-github-subject")
	attacker := createIdentityTestAccount(t, service, IdentityProviderGoogle, "attacker-google-subject")

	ownerGoogle, err := service.LinkCredential(owner.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{
			Kind:       IdentityCredentialOAuth,
			Provider:   IdentityProviderGoogle,
			Identifier: "shared-google-subject",
			Verified:   true,
		},
		ActorID: owner.AccountID,
	})
	if err != nil {
		t.Fatalf("establish owner credential: %v", err)
	}

	_, err = service.LinkCredential(attacker.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{
			Kind:       IdentityCredentialOAuth,
			Provider:   IdentityProviderGoogle,
			Identifier: "shared-google-subject",
			Verified:   true,
		},
		ActorID: attacker.AccountID,
	})
	requireIdentityCode(t, err, "credential_link_conflict")

	authenticated, err := service.Authenticate(IdentityCredentialInput{
		Kind:       IdentityCredentialOAuth,
		Provider:   IdentityProviderGoogle,
		Identifier: "shared-google-subject",
		Verified:   true,
	})
	if err != nil {
		t.Fatalf("authenticate original owner: %v", err)
	}
	if authenticated.Account.AccountID != owner.AccountID ||
		authenticated.Credential.CredentialID != ownerGoogle.CredentialID {
		t.Fatalf("credential ownership changed after conflict: %#v", authenticated)
	}
}

func TestUnifiedIdentityHTTPContractUnlinkPreservesMembershipAndFinalLogin(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "membership-github-subject")
	githubCredential := account.Credentials[0]

	google, err := service.LinkCredential(account.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{
			Kind:       IdentityCredentialOAuth,
			Provider:   IdentityProviderGoogle,
			Identifier: "membership-google-subject",
			Verified:   true,
		},
		ActorID: account.AccountID,
	})
	if err != nil {
		t.Fatalf("link Google credential: %v", err)
	}
	membership, err := service.AddMembership(account.AccountID, IdentityMembershipRequest{
		TenantID:  "tenant_identity_contract",
		ProjectID: "project_identity_contract",
		Role:      "owner",
		ActorID:   account.AccountID,
	})
	if err != nil {
		t.Fatalf("add membership: %v", err)
	}

	if _, err := service.UnlinkCredential(account.AccountID, githubCredential.CredentialID, account.AccountID); err != nil {
		t.Fatalf("unlink non-final credential: %v", err)
	}
	afterUnlink, err := service.GetAccount(account.AccountID)
	if err != nil {
		t.Fatalf("get account after unlink: %v", err)
	}
	if afterUnlink.CredentialCount != 1 ||
		afterUnlink.Credentials[0].CredentialID != google.CredentialID {
		t.Fatalf("unexpected remaining credential: %#v", afterUnlink.Credentials)
	}
	if afterUnlink.MembershipCount != 1 ||
		afterUnlink.Memberships[0].MembershipID != membership.MembershipID {
		t.Fatalf("credential unlink changed membership authorization: %#v", afterUnlink.Memberships)
	}

	_, err = service.UnlinkCredential(account.AccountID, google.CredentialID, account.AccountID)
	requireIdentityCode(t, err, "last_login_credential")
	final, err := service.GetAccount(account.AccountID)
	if err != nil {
		t.Fatalf("get account after rejected final unlink: %v", err)
	}
	if final.CredentialCount != 1 || final.MembershipCount != 1 {
		t.Fatalf("rejected final unlink mutated account: %#v", final)
	}
}

func assertUnifiedIdentityPublicPayload(t *testing.T, payload any, forbiddenValues ...string) {
	t.Helper()
	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal public identity payload: %v", err)
	}
	text := strings.ToLower(string(encoded))
	for _, key := range []string{
		`"provider_subject"`,
		`"subject"`,
		`"subject_digest"`,
		`"provider_subject_sha256"`,
		`"identifier_sha256"`,
		`"access_token"`,
		`"refresh_token"`,
		`"id_token"`,
		`"token"`,
		`"token_ref"`,
		`"authorization_code"`,
		`"code_verifier"`,
		`"client_secret"`,
		`"state"`,
		`"nonce"`,
		`"email"`,
		`"phone"`,
	} {
		if strings.Contains(text, key) {
			t.Fatalf("public identity payload exposed forbidden key %s: %s", key, encoded)
		}
	}
	for _, value := range forbiddenValues {
		if value != "" && strings.Contains(string(encoded), value) {
			t.Fatalf("public identity payload exposed private value %q: %s", value, encoded)
		}
	}
}
