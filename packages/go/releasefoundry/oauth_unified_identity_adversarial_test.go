package releasefoundry

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type adversarialOAuthProvider struct {
	name        string
	subject     string
	email       string
	revokeCalls atomic.Int32
}

func (provider *adversarialOAuthProvider) Name() string { return provider.name }

func (provider *adversarialOAuthProvider) SchemaVersion() string {
	return "releasefoundry." + provider.name + "_oauth.v1"
}

func (provider *adversarialOAuthProvider) ExactScopes() []string {
	return []string{"email", "openid", "profile"}
}

func (provider *adversarialOAuthProvider) AuthorizationURL(request OAuthAuthorizationRequest) (string, error) {
	return unifiedOAuthTestAdapter{name: provider.name}.AuthorizationURL(request)
}

func (provider *adversarialOAuthProvider) ExchangeCode(context.Context, OAuthCodeExchangeRequest) (OAuthTokenSet, error) {
	return OAuthTokenSet{
		AccessToken: "private-access-token",
		IDToken:     "private-id-token",
		TokenType:   "Bearer",
		Scopes:      provider.ExactScopes(),
	}, nil
}

func (provider *adversarialOAuthProvider) ResolveIdentity(context.Context, OAuthIdentityRequest) (OAuthProviderIdentity, error) {
	return OAuthProviderIdentity{
		Subject:       provider.subject,
		DisplayName:   "Adversarial Identity",
		Email:         provider.email,
		EmailVerified: true,
	}, nil
}

func (provider *adversarialOAuthProvider) RevokeToken(context.Context, OAuthClientCredentials, string) error {
	provider.revokeCalls.Add(1)
	return nil
}

type adversarialOAuthStore struct {
	*MemoryOAuthStore
	deleteCalls     atomic.Int32
	disconnectCalls atomic.Int32
}

func newAdversarialOAuthStore() *adversarialOAuthStore {
	return &adversarialOAuthStore{MemoryOAuthStore: NewMemoryOAuthStore()}
}

func (store *adversarialOAuthStore) DeleteOAuthToken(ctx context.Context, ref string) error {
	store.deleteCalls.Add(1)
	return store.MemoryOAuthStore.DeleteOAuthToken(ctx, ref)
}

func (store *adversarialOAuthStore) DisconnectOAuthConnection(
	ctx context.Context,
	binding OAuthSecretBinding,
	at time.Time,
) (OAuthConnection, error) {
	store.disconnectCalls.Add(1)
	return store.MemoryOAuthStore.DisconnectOAuthConnection(ctx, binding, at)
}

func TestOAuthAdversarialLastCredentialDisconnectRejectsBeforeProviderOrStoreMutation(t *testing.T) {
	identity := newUnifiedOAuthTestIdentity(t)
	store := newAdversarialOAuthStore()
	provider := &adversarialOAuthProvider{
		name:    "google",
		subject: "only-login-subject",
		email:   "private-only@example.invalid",
	}
	service := newAdversarialOAuthService(
		t,
		provider,
		OAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session", AccountID: "account"},
		store,
		store,
		store,
		identity,
		0x11,
	)
	connected := completeUnifiedOAuthFlow(t, service, "account")

	_, err := service.Disconnect(
		context.Background(),
		httptest.NewRequest(http.MethodPost, "/disconnect", nil),
		"tenant",
		"project",
		"account",
	)
	requireOAuthStatusCode(t, err, http.StatusConflict, "last_login_credential")

	if got := provider.revokeCalls.Load(); got != 0 {
		t.Fatalf("provider revoke called before final-credential rejection: calls=%d", got)
	}
	if got := store.deleteCalls.Load(); got != 0 {
		t.Fatalf("secret delete called before final-credential rejection: calls=%d", got)
	}
	if got := store.disconnectCalls.Load(); got != 0 {
		t.Fatalf("connection disconnect called before final-credential rejection: calls=%d", got)
	}
	if _, err := store.GetOAuthToken(context.Background(), connected.Connection.TokenRef); err != nil {
		t.Fatalf("final-credential rejection removed provider token: %v", err)
	}
	account, err := identity.GetAccount("account")
	if err != nil {
		t.Fatal(err)
	}
	if account.CredentialCount != 1 ||
		account.Credentials[0].CredentialID != connected.Connection.CredentialID {
		t.Fatalf("final-credential rejection mutated canonical identity: %#v", account)
	}
}

func TestOAuthAdversarialTwoCredentialsDisconnectsOnlyProviderAndPreservesMembership(t *testing.T) {
	identity := newUnifiedOAuthTestIdentity(t)
	store := newAdversarialOAuthStore()
	provider := &adversarialOAuthProvider{
		name:    "github",
		subject: "github-subject-to-disconnect",
		email:   "private-github@example.invalid",
	}
	service := newAdversarialOAuthService(
		t,
		provider,
		OAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session", AccountID: "account"},
		store,
		store,
		store,
		identity,
		0x22,
	)
	connected := completeUnifiedOAuthFlow(t, service, "account")
	backup, err := identity.LinkCredential("account", LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{
			Kind:       IdentityCredentialEmail,
			Provider:   IdentityProviderLocal,
			Identifier: "backup@example.invalid",
			Verified:   true,
		},
		ActorID: "user",
	})
	if err != nil {
		t.Fatal(err)
	}
	membership, err := identity.AddMembership("account", IdentityMembershipRequest{
		TenantID: "tenant", ProjectID: "project", Role: "owner", ActorID: "user",
	})
	if err != nil {
		t.Fatal(err)
	}

	result, err := service.Disconnect(
		context.Background(),
		httptest.NewRequest(http.MethodPost, "/disconnect", nil),
		"tenant",
		"project",
		"account",
	)
	if err != nil {
		t.Fatalf("disconnect non-final credential: %v", err)
	}
	if !result.Disconnected || result.Connection.CredentialID != connected.Connection.CredentialID {
		t.Fatalf("unexpected disconnect result: %#v", result)
	}
	if provider.revokeCalls.Load() != 1 || store.deleteCalls.Load() != 1 || store.disconnectCalls.Load() != 1 {
		t.Fatalf(
			"disconnect side effects were not exactly once: revoke=%d delete=%d disconnect=%d",
			provider.revokeCalls.Load(),
			store.deleteCalls.Load(),
			store.disconnectCalls.Load(),
		)
	}

	account, err := identity.GetAccount("account")
	if err != nil {
		t.Fatal(err)
	}
	if account.CredentialCount != 1 || account.Credentials[0].CredentialID != backup.CredentialID {
		t.Fatalf("disconnect removed the wrong credential: %#v", account.Credentials)
	}
	if account.MembershipCount != 1 ||
		account.Memberships[0].MembershipID != membership.MembershipID ||
		account.Memberships[0].Role != "owner" {
		t.Fatalf("credential disconnect changed membership authorization: %#v", account.Memberships)
	}
}

func TestOAuthAdversarialMissingTrustedSessionAccountIsUnauthorizedWithoutSideEffects(t *testing.T) {
	identity := newUnifiedOAuthTestIdentity(t)
	store := newAdversarialOAuthStore()
	provider := &adversarialOAuthProvider{name: "google", subject: "subject"}
	service := newAdversarialOAuthService(
		t,
		provider,
		OAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session"},
		store,
		store,
		store,
		identity,
		0x33,
	)

	_, err := service.Start(
		context.Background(),
		httptest.NewRequest(http.MethodPost, "/start", nil),
		"tenant",
		"project",
		"caller-asserted-account",
	)
	requireOAuthStatusCode(t, err, http.StatusUnauthorized, "session_account_missing")
	if provider.revokeCalls.Load() != 0 || store.deleteCalls.Load() != 0 || store.disconnectCalls.Load() != 0 {
		t.Fatal("missing trusted account triggered provider or store side effects")
	}
}

func TestOAuthAdversarialMatchingProviderEmailDoesNotAutoMergeAccounts(t *testing.T) {
	identity := newUnifiedOAuthTestIdentity(t)
	const sharedEmail = "same-private-email@example.invalid"

	first := newAdversarialOAuthService(
		t,
		&adversarialOAuthProvider{name: "github", subject: "github-subject", email: sharedEmail},
		OAuthSession{TenantID: "tenant", UserID: "first-user", SessionID: "first-session", AccountID: "first-account"},
		newAdversarialOAuthStore(),
		newAdversarialOAuthStore(),
		newAdversarialOAuthStore(),
		identity,
		0x44,
	)
	secondStore := newAdversarialOAuthStore()
	second := newAdversarialOAuthService(
		t,
		&adversarialOAuthProvider{name: "google", subject: "google-subject", email: sharedEmail},
		OAuthSession{TenantID: "tenant", UserID: "second-user", SessionID: "second-session", AccountID: "second-account"},
		secondStore,
		secondStore,
		secondStore,
		identity,
		0x55,
	)

	firstResult := completeUnifiedOAuthFlow(t, first, "first-account")
	secondResult := completeUnifiedOAuthFlow(t, second, "second-account")
	if firstResult.Connection.AccountID != "first-account" ||
		secondResult.Connection.AccountID != "second-account" {
		t.Fatalf("matching email auto-merged accounts: first=%#v second=%#v", firstResult, secondResult)
	}
	firstAccount, err := identity.GetAccount("first-account")
	if err != nil {
		t.Fatal(err)
	}
	secondAccount, err := identity.GetAccount("second-account")
	if err != nil {
		t.Fatal(err)
	}
	if firstAccount.PrimaryID == secondAccount.PrimaryID {
		t.Fatalf("matching email collapsed distinct principals: first=%#v second=%#v", firstAccount, secondAccount)
	}
}

func TestOAuthAdversarialPublicPayloadOmitsDigestTokenAndEmail(t *testing.T) {
	identity := newUnifiedOAuthTestIdentity(t)
	store := newAdversarialOAuthStore()
	const (
		privateSubject = "private-provider-subject"
		privateEmail   = "private-person@example.invalid"
	)
	service := newAdversarialOAuthService(
		t,
		&adversarialOAuthProvider{name: "google", subject: privateSubject, email: privateEmail},
		OAuthSession{TenantID: "tenant", UserID: "user", SessionID: "session", AccountID: "account"},
		store,
		store,
		store,
		identity,
		0x66,
	)
	result := completeUnifiedOAuthFlow(t, service, "account")
	account, err := identity.GetAccount("account")
	if err != nil {
		t.Fatal(err)
	}

	payload := struct {
		Callback OAuthCallbackResult `json:"callback"`
		Account  IdentityAccountDTO  `json:"account"`
	}{Callback: result, Account: account}
	assertUnifiedIdentityPublicPayload(
		t,
		payload,
		privateSubject,
		privateEmail,
		"private-access-token",
		"private-id-token",
		result.Connection.ProviderSubjectHash,
		result.Connection.TokenRef,
	)
	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(strings.ToLower(string(encoded)), "digest") {
		t.Fatalf("public payload exposed a digest field: %s", encoded)
	}
}

func TestOAuthAdversarialConcurrentSubjectOwnershipConflictHasSingleWinner(t *testing.T) {
	identity := newUnifiedOAuthTestIdentity(t)
	const sharedSubject = "one-provider-subject"
	type raceContender struct {
		accountID string
		service   *OAuthService
	}
	contenders := make([]raceContender, 0, 2)
	for index, accountID := range []string{"account-one", "account-two"} {
		store := newAdversarialOAuthStore()
		session := OAuthSession{
			TenantID: "tenant", UserID: "user-" + accountID,
			SessionID: "session-" + accountID, AccountID: accountID,
		}
		contenders = append(contenders, raceContender{
			accountID: accountID,
			service: newAdversarialOAuthService(
				t,
				&adversarialOAuthProvider{name: "google", subject: sharedSubject, email: "shared@example.invalid"},
				session,
				store,
				store,
				store,
				identity,
				byte(0x70+index),
			),
		})
	}

	start := make(chan struct{})
	results := make(chan struct {
		accountID string
		result    OAuthCallbackResult
		err       error
	}, len(contenders))
	var wait sync.WaitGroup
	for _, contender := range contenders {
		wait.Add(1)
		go func(contender raceContender) {
			defer wait.Done()
			<-start
			result, err := startAndCallbackUnifiedOAuth(contender.service, contender.accountID)
			results <- struct {
				accountID string
				result    OAuthCallbackResult
				err       error
			}{accountID: contender.accountID, result: result, err: err}
		}(contender)
	}
	close(start)
	wait.Wait()
	close(results)

	var winner string
	successes, conflicts := 0, 0
	for result := range results {
		if result.err == nil {
			successes++
			winner = result.accountID
			if result.result.Connection.AccountID != result.accountID {
				t.Fatalf("winner connection changed account ownership: %#v", result.result)
			}
			continue
		}
		var oauthError OAuthError
		if errors.As(result.err, &oauthError) &&
			oauthError.Status == http.StatusConflict &&
			oauthError.Code == "credential_link_conflict" {
			conflicts++
			continue
		}
		t.Fatalf("unexpected concurrent callback error for %s: %v", result.accountID, result.err)
	}
	if successes != 1 || conflicts != 1 {
		t.Fatalf("expected one owner and one conflict, got successes=%d conflicts=%d", successes, conflicts)
	}
	authenticated, err := identity.Authenticate(IdentityCredentialInput{
		Kind: IdentityCredentialOAuth, Provider: IdentityProviderGoogle,
		Identifier: sharedSubject, Verified: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if authenticated.Account.AccountID != winner {
		t.Fatalf("provider subject owner changed after race: winner=%s authenticated=%s", winner, authenticated.Account.AccountID)
	}
}

func newAdversarialOAuthService(
	t *testing.T,
	provider OAuthProviderAdapter,
	session OAuthSession,
	transactions OAuthTransactionStore,
	secrets OAuthSecretStore,
	connections OAuthConnectionStore,
	identity *UnifiedIdentityService,
	randomByte byte,
) *OAuthService {
	t.Helper()
	service, err := NewOAuthService(OAuthServiceOptions{
		Provider:        provider,
		SessionResolver: oauthTestSessionResolver{session: session},
		Credentials:     oauthTestCredentials{},
		Transactions:    transactions,
		Secrets:         secrets,
		Connections:     connections,
		IdentityBridge:  UnifiedIdentityOAuthBridge{Identity: identity},
		CallbackURL:     "http://localhost:8787/oauth/" + provider.Name() + "/callback",
		TransactionTTL:  time.Minute,
		Now: func() time.Time {
			return time.Date(2026, 7, 10, 12, 0, 0, 0, time.UTC)
		},
		Random: bytes.NewReader(bytes.Repeat([]byte{randomByte}, 256)),
	})
	if err != nil {
		t.Fatalf("new adversarial %s OAuth service: %v", provider.Name(), err)
	}
	return service
}

func requireOAuthStatusCode(t *testing.T, err error, status int, code string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected OAuth error status=%d code=%s", status, code)
	}
	var oauthError OAuthError
	if !errors.As(err, &oauthError) {
		t.Fatalf("expected OAuthError, got %T: %v", err, err)
	}
	if oauthError.Status != status || oauthError.Code != code {
		t.Fatalf(
			"OAuth error status/code=%d/%s want=%d/%s error=%v",
			oauthError.Status,
			oauthError.Code,
			status,
			code,
			oauthError,
		)
	}
}
