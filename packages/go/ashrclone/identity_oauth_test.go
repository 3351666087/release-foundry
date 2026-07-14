package ashrclone

import (
	"context"
	"encoding/json"
	"errors"
	"net/url"
	"strings"
	"testing"
	"time"
)

type oauthAdapterStub struct {
	authorizationRequest OAuthAuthorizationRequest
	exchangeRequest      OAuthTokenExchangeRequest
	identity             OAuthProviderIdentity
	authorizationErr     error
	exchangeErr          error
}

func (adapter *oauthAdapterStub) BuildAuthorizationURL(_ context.Context, request OAuthAuthorizationRequest) (string, error) {
	adapter.authorizationRequest = request
	if adapter.authorizationErr != nil {
		return "", adapter.authorizationErr
	}
	values := url.Values{
		"state":                 {request.State},
		"code_challenge":        {request.CodeChallenge},
		"code_challenge_method": {request.CodeChallengeMethod},
		"redirect_uri":          {request.RedirectURI},
	}
	return "https://provider.example/authorize?" + values.Encode(), nil
}

func (adapter *oauthAdapterStub) ExchangeAuthorizationCode(_ context.Context, request OAuthTokenExchangeRequest) (OAuthProviderIdentity, error) {
	adapter.exchangeRequest = request
	if adapter.exchangeErr != nil {
		return OAuthProviderIdentity{}, adapter.exchangeErr
	}
	return adapter.identity, nil
}

func newOAuthCoordinatorForTest(
	t *testing.T,
	now func() time.Time,
	identity *IdentityService,
	adapters map[string]OAuthProviderAdapter,
	redirects map[string][]string,
) *OAuthFlowCoordinator {
	t.Helper()
	coordinator, err := newOAuthFlowCoordinatorWithClockAndKey(
		identity,
		adapters,
		redirects,
		now,
		[]byte("0123456789abcdef0123456789abcdef"),
	)
	if err != nil {
		t.Fatalf("new OAuth coordinator: %v", err)
	}
	return coordinator
}

func TestOAuthFlowRequiresExactRedirectStateAndPKCE(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	identity := NewIdentityServiceWithClock(func() time.Time { return now })
	account := registerIdentityAccount(t, identity, "owner@qq.com")
	adapter := &oauthAdapterStub{identity: OAuthProviderIdentity{
		Provider:        "qq",
		ProviderSubject: "qq-private-subject",
	}}
	coordinator := newOAuthCoordinatorForTest(
		t,
		func() time.Time { return now },
		identity,
		map[string]OAuthProviderAdapter{"qq": adapter},
		map[string][]string{"qq": {"https://console.ashr.example/oauth/callback"}},
	)

	if _, err := coordinator.Begin(
		context.Background(),
		"qq",
		OAuthIntentLink,
		"https://attacker.example/oauth/callback",
		account.AccountID,
	); err == nil {
		t.Fatal("unlisted redirect URI must be rejected")
	} else if oauthErr, ok := err.(*OAuthFlowError); !ok || oauthErr.Code != OAuthRedirectNotAllowed {
		t.Fatalf("unexpected redirect rejection: %T %v", err, err)
	}
	begin, err := coordinator.Begin(
		context.Background(),
		"QQ",
		OAuthIntentLink,
		"https://console.ashr.example/oauth/callback",
		account.AccountID,
	)
	if err != nil {
		t.Fatalf("begin OAuth link: %v", err)
	}
	if begin.FlowID == "" || begin.AuthorizationURL == "" || begin.Provider != "qq" {
		t.Fatalf("unsafe or incomplete OAuth begin result: %+v", begin)
	}
	if adapter.authorizationRequest.State == "" ||
		adapter.authorizationRequest.CodeChallenge == "" ||
		adapter.authorizationRequest.CodeChallengeMethod != "S256" {
		t.Fatalf("state or PKCE missing: %+v", adapter.authorizationRequest)
	}
	record := coordinator.flows[begin.FlowID]
	if record.PKCEVerifier == "" || record.PKCEVerifier == adapter.authorizationRequest.CodeChallenge {
		t.Fatal("PKCE verifier must remain server-side and differ from its S256 challenge")
	}
	if record.StateHash == oauthStateHMAC(coordinator.stateHMACKey, "") {
		t.Fatal("OAuth state hash was not persisted")
	}

	if _, err := coordinator.Complete(
		context.Background(),
		begin.FlowID,
		"attacker-state",
		"authorization-code",
	); err == nil {
		t.Fatal("state mismatch must be rejected")
	}
	if _, exists := coordinator.flows[begin.FlowID]; !exists {
		t.Fatal("state mismatch must not consume the legitimate flow")
	}
	completed, err := coordinator.Complete(
		context.Background(),
		begin.FlowID,
		adapter.authorizationRequest.State,
		"authorization-code",
	)
	if err != nil {
		t.Fatalf("complete OAuth flow: %v", err)
	}
	if completed.AccountID != account.AccountID || completed.Intent != OAuthIntentLink {
		t.Fatalf("OAuth intent/account context was not preserved: %+v", completed)
	}
	if adapter.exchangeRequest.PKCEVerifier != record.PKCEVerifier ||
		adapter.exchangeRequest.RedirectURI != record.RedirectURI {
		t.Fatalf("token exchange did not use bound PKCE/redirect context: %+v", adapter.exchangeRequest)
	}
	if _, err := coordinator.Complete(
		context.Background(),
		begin.FlowID,
		adapter.authorizationRequest.State,
		"authorization-code",
	); err == nil {
		t.Fatal("OAuth flow replay must fail")
	}
}

func TestOAuthExchangeFailureIsSanitizedAndConsumesFlow(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	identity := NewIdentityServiceWithClock(func() time.Time { return now })
	adapter := &oauthAdapterStub{
		exchangeErr: errors.New("provider response leaked client_secret=private-value access_token=private-token"),
	}
	coordinator := newOAuthCoordinatorForTest(
		t,
		func() time.Time { return now },
		identity,
		map[string]OAuthProviderAdapter{"wechat_open": adapter},
		map[string][]string{"wechat_open": {"https://console.ashr.example/oauth/callback"}},
	)
	begin, err := coordinator.Begin(
		context.Background(),
		"wechat_open",
		OAuthIntentLogin,
		"https://console.ashr.example/oauth/callback",
		"",
	)
	if err != nil {
		t.Fatalf("begin OAuth login: %v", err)
	}
	_, err = coordinator.Complete(
		context.Background(),
		begin.FlowID,
		adapter.authorizationRequest.State,
		"private-authorization-code",
	)
	if err == nil {
		t.Fatal("provider exchange failure must fail closed")
	}
	if oauthErr, ok := err.(*OAuthFlowError); !ok || oauthErr.Code != OAuthExchangeFailed {
		t.Fatalf("unexpected exchange error: %T %v", err, err)
	}
	for _, forbidden := range []string{"client_secret", "private-value", "access_token", "private-token"} {
		if strings.Contains(err.Error(), forbidden) {
			t.Fatalf("OAuth error leaked provider details %q: %v", forbidden, err)
		}
	}
	if _, exists := coordinator.flows[begin.FlowID]; exists {
		t.Fatal("failed token exchange must still consume the one-time OAuth flow")
	}
}

func TestOAuthLinkIssuesOnlyOpaqueAccountBoundBindingTicket(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	identity := NewIdentityServiceWithClock(func() time.Time { return now })
	first := registerIdentityAccount(t, identity, "first@163.com")
	second := registerIdentityAccount(t, identity, "second@126.com")
	adapter := &oauthAdapterStub{identity: OAuthProviderIdentity{
		Provider:        "wechat_open",
		ProviderSubject: "wechat-private-subject",
		ProviderUnionID: "wechat-private-union",
		VerifiedEmail:   first.PrimaryEmail,
	}}
	coordinator := newOAuthCoordinatorForTest(
		t,
		func() time.Time { return now },
		identity,
		map[string]OAuthProviderAdapter{"wechat_open": adapter},
		map[string][]string{"wechat_open": {"https://console.ashr.example/oauth/callback"}},
	)
	begin, err := coordinator.Begin(
		context.Background(),
		"wechat_open",
		OAuthIntentLink,
		"https://console.ashr.example/oauth/callback",
		second.AccountID,
	)
	if err != nil {
		t.Fatalf("begin OAuth link: %v", err)
	}
	completion, err := coordinator.CompleteLink(
		context.Background(),
		begin.FlowID,
		adapter.authorizationRequest.State,
		"authorization-code",
	)
	if err != nil {
		t.Fatalf("complete OAuth link: %v", err)
	}
	if completion.BindingTicket.TicketID == "" || completion.BindingTicket.Secret == "" {
		t.Fatalf("opaque binding ticket missing: %+v", completion)
	}
	encoded, err := json.Marshal(completion)
	if err != nil {
		t.Fatalf("marshal OAuth link completion: %v", err)
	}
	for _, forbidden := range []string{
		completion.BindingTicket.Secret,
		"wechat-private-subject",
		"wechat-private-union",
		first.PrimaryEmail,
		"provider_subject",
		"verified_email",
	} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("OAuth link response leaked %q: %s", forbidden, encoded)
		}
	}
	if _, err := identity.BindCredentialWithTicket(
		first.AccountID,
		first.AccountID,
		completion.BindingTicket.TicketID,
		completion.BindingTicket.Secret,
		true,
		true,
	); err == nil {
		t.Fatal("matching verified email must not auto-link ticket to another account")
	}
	if _, err := identity.BindCredentialWithTicket(
		second.AccountID,
		second.AccountID,
		completion.BindingTicket.TicketID,
		completion.BindingTicket.Secret,
		true,
		true,
	); err != nil {
		t.Fatalf("explicitly selected canonical account could not bind: %v", err)
	}
}

func TestOAuthRegistrationAndLoginIntentsDoNotMutateCanonicalAccounts(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	identity := NewIdentityServiceWithClock(func() time.Time { return now })
	adapters := map[string]OAuthProviderAdapter{
		"qq": &oauthAdapterStub{identity: OAuthProviderIdentity{
			Provider:        "qq",
			ProviderSubject: "qq-registration-subject",
			VerifiedEmail:   "owner@163.com",
		}},
		"wechat_open": &oauthAdapterStub{identity: OAuthProviderIdentity{
			Provider:        "wechat_open",
			ProviderSubject: "wechat-login-subject",
		}},
	}
	coordinator := newOAuthCoordinatorForTest(
		t,
		func() time.Time { return now },
		identity,
		adapters,
		map[string][]string{
			"qq":          {"https://console.ashr.example/oauth/callback"},
			"wechat_open": {"https://console.ashr.example/oauth/callback"},
		},
	)
	for provider, intent := range map[string]OAuthIntent{
		"qq":          OAuthIntentRegistration,
		"wechat_open": OAuthIntentLogin,
	} {
		adapter := adapters[provider].(*oauthAdapterStub)
		begin, err := coordinator.Begin(
			context.Background(),
			provider,
			intent,
			"https://console.ashr.example/oauth/callback",
			"",
		)
		if err != nil {
			t.Fatalf("begin %s %s: %v", provider, intent, err)
		}
		completed, err := coordinator.Complete(
			context.Background(),
			begin.FlowID,
			adapter.authorizationRequest.State,
			"authorization-code",
		)
		if err != nil {
			t.Fatalf("complete %s %s: %v", provider, intent, err)
		}
		if completed.Intent != intent || completed.Provider != provider {
			t.Fatalf("explicit intent/provider lost: %+v", completed)
		}
	}
	if identity.AccountCount() != 0 {
		t.Fatal("OAuth validation alone must never auto-register, auto-link, or merge canonical accounts")
	}
}

func TestOAuthFlowExpiresAndRejectsUnsafeRedirectSchemes(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	identity := NewIdentityServiceWithClock(func() time.Time { return now })
	if _, err := newOAuthFlowCoordinatorWithClockAndKey(
		identity,
		map[string]OAuthProviderAdapter{"qq": &oauthAdapterStub{}},
		map[string][]string{"qq": {"http://console.ashr.example/oauth/callback"}},
		func() time.Time { return now },
		[]byte("0123456789abcdef0123456789abcdef"),
	); err == nil {
		t.Fatal("non-loopback HTTP redirect must be rejected even when configured")
	}
	adapter := &oauthAdapterStub{identity: OAuthProviderIdentity{
		Provider:        "qq",
		ProviderSubject: "qq-private-subject",
	}}
	coordinator := newOAuthCoordinatorForTest(
		t,
		func() time.Time { return now },
		identity,
		map[string]OAuthProviderAdapter{"qq": adapter},
		map[string][]string{"qq": {"http://127.0.0.1:3000/oauth/callback"}},
	)
	begin, err := coordinator.Begin(
		context.Background(),
		"qq",
		OAuthIntentLogin,
		"http://127.0.0.1:3000/oauth/callback",
		"",
	)
	if err != nil {
		t.Fatalf("loopback development redirect should be allowed: %v", err)
	}
	now = begin.ExpiresAt
	if _, err := coordinator.Complete(
		context.Background(),
		begin.FlowID,
		adapter.authorizationRequest.State,
		"authorization-code",
	); err == nil {
		t.Fatal("expired OAuth flow must fail")
	}
	if _, exists := coordinator.flows[begin.FlowID]; !exists {
		t.Fatal("expiry rejection should not mutate the flow map outside pruning")
	}
	now = now.Add(time.Second)
	if _, err := coordinator.Begin(
		context.Background(),
		"qq",
		OAuthIntentLogin,
		"http://127.0.0.1:3000/oauth/callback",
		"",
	); err != nil {
		t.Fatalf("begin after expiry: %v", err)
	}
	if _, exists := coordinator.flows[begin.FlowID]; exists {
		t.Fatal("begin must prune abandoned expired OAuth flows")
	}
}
