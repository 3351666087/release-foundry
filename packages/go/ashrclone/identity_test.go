package ashrclone

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"
)

func registerIdentityAccount(t *testing.T, service *IdentityService, email string) CanonicalAccount {
	t.Helper()
	challenge, err := service.BeginEmailRegistration(email, "", "")
	if err != nil {
		t.Fatalf("begin registration: %v", err)
	}
	account, err := service.CompleteEmailRegistration(CompleteRegistrationRequest{
		ChallengeID: challenge.ChallengeID,
		Secret:      challenge.Secret,
		DisplayName: "Owner",
	})
	if err != nil {
		t.Fatalf("complete registration: %v", err)
	}
	return account
}

func TestIdentityRegistrationAndLoginAreSeparate(t *testing.T) {
	service := NewIdentityService()

	unknownLogin, err := service.BeginEmailLogin("new-user@163.com")
	if err != nil {
		t.Fatalf("begin login: %v", err)
	}
	if _, err := service.CompleteEmailLogin(unknownLogin.ChallengeID, unknownLogin.Secret); err == nil {
		t.Fatal("unknown login must fail instead of registering")
	}
	if service.AccountCount() != 0 {
		t.Fatal("login must never create a canonical account")
	}

	account := registerIdentityAccount(t, service, "new-user@163.com")
	if account.Region != "cn" || account.Locale != "zh-CN" {
		t.Fatalf("domestic email defaults not applied: %+v", account)
	}
	if _, err := service.BeginEmailRegistration("new-user@163.com", "", ""); err == nil {
		t.Fatal("registration must not silently become login")
	}

	login, err := service.BeginEmailLogin("new-user@163.com")
	if err != nil {
		t.Fatalf("begin known login: %v", err)
	}
	result, err := service.CompleteEmailLogin(login.ChallengeID, login.Secret)
	if err != nil {
		t.Fatalf("complete login: %v", err)
	}
	if result.Status != "authenticated" || result.AccountID != account.AccountID || result.SessionToken == "" {
		t.Fatalf("unexpected login result: %+v", result)
	}
}

func TestIdentityCanonicalAccountRequiresExplicitCredentialBinding(t *testing.T) {
	service := NewIdentityService()
	account := registerIdentityAccount(t, service, "owner@qq.com")
	request := BindCredentialRequest{
		Provider:        "wechat_open",
		ProviderSubject: "wechat-subject-private",
		ProviderUnionID: "wechat-union-private",
		VerifiedEmail:   "owner@qq.com",
	}

	if _, err := service.BindCredential(account.AccountID, account.AccountID, request); err == nil {
		t.Fatal("binding without explicit consent and reauthentication must fail")
	}
	request.ExplicitConsent = true
	if _, err := service.BindCredential(account.AccountID, account.AccountID, request); err == nil {
		t.Fatal("binding without reauthentication must fail")
	}
	request.Reauthenticated = true
	credential, err := service.BindCredential(account.AccountID, account.AccountID, request)
	if err != nil {
		t.Fatalf("bind credential: %v", err)
	}
	if credential.ProviderSubjectFingerprint == request.ProviderSubject || credential.ProviderUnionFingerprint == request.ProviderUnionID {
		t.Fatal("provider subjects must be fingerprinted")
	}
	credentialJSON, _ := json.Marshal(credential)
	for _, forbidden := range []string{
		credential.ProviderSubjectFingerprint,
		credential.ProviderUnionFingerprint,
		credential.VerifiedEmail,
		"provider_subject_fingerprint",
		"verified_email",
	} {
		if forbidden != "" && strings.Contains(string(credentialJSON), forbidden) {
			t.Fatalf("credential JSON leaked private binding data %q: %s", forbidden, credentialJSON)
		}
	}
	view, err := service.A3View(account.AccountID)
	if err != nil {
		t.Fatalf("a3 view: %v", err)
	}
	if len(view.Credentials) != 2 || view.PrimaryEmailHint == account.PrimaryEmail {
		t.Fatalf("unsafe or incomplete A3 view: %+v", view)
	}
	encoded, _ := json.Marshal(view)
	public := string(encoded)
	for _, forbidden := range []string{"wechat-subject-private", "wechat-union-private", "owner@qq.com", "provider_subject"} {
		if strings.Contains(public, forbidden) {
			t.Fatalf("A3 view leaked %q: %s", forbidden, public)
		}
	}
}

func TestIdentityMatchingVerifiedEmailNeverAutoLinksAccounts(t *testing.T) {
	service := NewIdentityService()
	first := registerIdentityAccount(t, service, "first@163.com")
	second := registerIdentityAccount(t, service, "second@126.com")

	request := BindCredentialRequest{
		Provider:        "qq",
		ProviderSubject: "same-oauth-subject",
		VerifiedEmail:   "shared@163.com",
		ExplicitConsent: true,
		Reauthenticated: true,
	}
	if _, err := service.BindCredential(first.AccountID, first.AccountID, request); err != nil {
		t.Fatalf("first bind: %v", err)
	}
	if _, err := service.BindCredential(second.AccountID, second.AccountID, request); err == nil {
		t.Fatal("one provider subject cannot be rebound to another canonical account")
	}
	if service.AccountCount() != 2 {
		t.Fatal("matching verified email must not merge canonical accounts")
	}
}

func TestIdentityTwoFactorIsOptionalRecommendedAndEnforcedWhenEnabled(t *testing.T) {
	service := NewIdentityService()
	account := registerIdentityAccount(t, service, "owner@foxmail.com")
	view, _ := service.A3View(account.AccountID)
	if view.TwoFactor.Enabled || !view.TwoFactor.Recommended {
		t.Fatalf("2FA should start optional but recommended: %+v", view.TwoFactor)
	}
	if _, err := service.EnableTwoFactor(account.AccountID, []string{"webauthn", "totp", "totp"}); err != nil {
		t.Fatalf("enable 2FA: %v", err)
	}

	login, _ := service.BeginEmailLogin(account.PrimaryEmail)
	firstFactor, err := service.CompleteEmailLogin(login.ChallengeID, login.Secret)
	if err != nil {
		t.Fatalf("first factor: %v", err)
	}
	if firstFactor.Status != "mfa_required" || firstFactor.SessionToken != "" || firstFactor.MFASecret == "" {
		t.Fatalf("MFA was not enforced: %+v", firstFactor)
	}
	authenticated, err := service.CompleteMFA(firstFactor.MFAChallengeID, firstFactor.MFASecret)
	if err != nil || authenticated.Status != "authenticated" {
		t.Fatalf("MFA completion failed: %+v %v", authenticated, err)
	}
}

func TestIdentityChallengeExpiryReplaySessionRotationAndRevocation(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	service := NewIdentityServiceWithClock(func() time.Time { return now })
	challenge, _ := service.BeginEmailRegistration("owner@example.cn", "", "")
	now = now.Add(11 * time.Minute)
	if _, err := service.CompleteEmailRegistration(CompleteRegistrationRequest{ChallengeID: challenge.ChallengeID, Secret: challenge.Secret}); err == nil {
		t.Fatal("expired registration proof must fail")
	}

	now = now.Add(time.Minute)
	account := registerIdentityAccount(t, service, "owner@example.cn")
	login, _ := service.BeginEmailLogin(account.PrimaryEmail)
	first, err := service.CompleteEmailLogin(login.ChallengeID, login.Secret)
	if err != nil {
		t.Fatalf("login: %v", err)
	}
	if _, err := service.CompleteEmailLogin(login.ChallengeID, login.Secret); err == nil {
		t.Fatal("login challenge replay must fail")
	}
	secondLogin, _ := service.BeginEmailLogin(account.PrimaryEmail)
	second, _ := service.CompleteEmailLogin(secondLogin.ChallengeID, secondLogin.Secret)
	if first.SessionID == second.SessionID || first.SessionToken == second.SessionToken {
		t.Fatal("new login must rotate session identity and secret")
	}
	if accountID, ok := service.VerifySession(first.SessionID, first.SessionToken); !ok || accountID != account.AccountID {
		t.Fatal("valid session was not accepted")
	}
	service.RevokeSession(first.SessionID)
	if _, ok := service.VerifySession(first.SessionID, first.SessionToken); ok {
		t.Fatal("revoked session must fail closed")
	}
}

func TestIdentityProviderCapabilitiesRetainDomesticOAuthAndPKCE(t *testing.T) {
	capabilities := IdentityProviderCapabilities()
	found := map[string]IdentityProviderCapability{}
	for _, capability := range capabilities {
		found[capability.Provider] = capability
	}
	for _, provider := range []string{"qq", "wechat_open"} {
		capability, ok := found[provider]
		if !ok || capability.Region != "cn" || !capability.Enabled || !capability.PKCERequired || !capability.SupportsExplicitBinding {
			t.Fatalf("missing domestic OAuth capability for %s: %+v", provider, capability)
		}
	}
}

func TestIdentityRandomSourceFailuresFailClosed(t *testing.T) {
	service := NewIdentityService()
	account := registerIdentityAccount(t, service, "owner@163.com")
	login, err := service.BeginEmailLogin(account.PrimaryEmail)
	if err != nil {
		t.Fatalf("begin login: %v", err)
	}
	service.secret = func() (string, error) {
		return "", errors.New("entropy unavailable")
	}
	if _, err := service.CompleteEmailLogin(login.ChallengeID, login.Secret); err == nil {
		t.Fatal("session creation must fail when secure randomness is unavailable")
	} else if identityErr, ok := err.(*IdentityError); !ok || identityErr.Code != IdentityUnavailable {
		t.Fatalf("unexpected session failure: %T %v", err, err)
	}
	if len(service.sessions) != 0 {
		t.Fatal("failed session creation must not persist a session")
	}
	if _, err := service.BeginEmailLogin(account.PrimaryEmail); err == nil {
		t.Fatal("challenge creation must fail when secure randomness is unavailable")
	} else if identityErr, ok := err.(*IdentityError); !ok || identityErr.Code != IdentityUnavailable {
		t.Fatalf("unexpected challenge failure: %T %v", err, err)
	}
}

func TestIdentityHashKeyRotationPreservesOldProofsAndSessions(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	keyOne := []byte("0123456789abcdef0123456789abcdef")
	keyTwo := []byte("fedcba9876543210fedcba9876543210")
	service, err := NewIdentityServiceWithHashKey(func() time.Time { return now }, "identity-hmac-2026-01", keyOne)
	if err != nil {
		t.Fatalf("new service with hash key: %v", err)
	}
	account := registerIdentityAccount(t, service, "owner@163.com")

	firstLogin, err := service.BeginEmailLogin(account.PrimaryEmail)
	if err != nil {
		t.Fatalf("begin first login: %v", err)
	}
	firstSession, err := service.CompleteEmailLogin(firstLogin.ChallengeID, firstLogin.Secret)
	if err != nil {
		t.Fatalf("complete first login: %v", err)
	}
	pendingLogin, err := service.BeginEmailLogin(account.PrimaryEmail)
	if err != nil {
		t.Fatalf("begin pending login: %v", err)
	}
	if service.sessions[firstSession.SessionID].TokenHashKeyID != "identity-hmac-2026-01" {
		t.Fatal("session did not record its issuing HMAC key ID")
	}
	if service.challenges[pendingLogin.ChallengeID].SecretHashKeyID != "identity-hmac-2026-01" {
		t.Fatal("challenge did not record its issuing HMAC key ID")
	}
	rawSHA := sha256.Sum256([]byte(firstSession.SessionToken))
	if rawSHA == service.sessions[firstSession.SessionID].TokenHash {
		t.Fatal("session tokens must use keyed HMAC rather than raw SHA-256")
	}

	if err := service.RotateHashKey("identity-hmac-2026-07", keyTwo); err != nil {
		t.Fatalf("rotate hash key: %v", err)
	}
	if accountID, ok := service.VerifySession(firstSession.SessionID, firstSession.SessionToken); !ok || accountID != account.AccountID {
		t.Fatal("session issued before rotation must remain valid")
	}
	secondSession, err := service.CompleteEmailLogin(pendingLogin.ChallengeID, pendingLogin.Secret)
	if err != nil {
		t.Fatalf("proof issued before rotation must remain valid: %v", err)
	}
	if service.sessions[secondSession.SessionID].TokenHashKeyID != "identity-hmac-2026-07" {
		t.Fatal("new session did not use the rotated active key")
	}
	if err := service.RetireHashKey("identity-hmac-2026-01"); err == nil {
		t.Fatal("key retirement must be blocked while an active session references the key")
	} else if identityErr, ok := err.(*IdentityError); !ok || identityErr.Code != IdentityHashKeyInUse {
		t.Fatalf("unexpected retirement error: %T %v", err, err)
	}

	service.RevokeSession(firstSession.SessionID)
	if err := service.RetireHashKey("identity-hmac-2026-01"); err != nil {
		t.Fatalf("retire inactive unused key: %v", err)
	}
	if _, exists := service.hashKeys["identity-hmac-2026-01"]; exists {
		t.Fatal("retired key remains installed")
	}
	if accountID, ok := service.VerifySession(secondSession.SessionID, secondSession.SessionToken); !ok || accountID != account.AccountID {
		t.Fatal("session issued by active key failed after old key retirement")
	}
}

func TestIdentityHashKeyRetirementWaitsForPendingChallenge(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	service, err := NewIdentityServiceWithHashKey(
		func() time.Time { return now },
		"identity-hmac-old",
		[]byte("0123456789abcdef0123456789abcdef"),
	)
	if err != nil {
		t.Fatalf("new service: %v", err)
	}
	challenge, err := service.BeginEmailRegistration("owner@qq.com", "", "")
	if err != nil {
		t.Fatalf("begin registration: %v", err)
	}
	if err := service.RotateHashKey("identity-hmac-new", []byte("fedcba9876543210fedcba9876543210")); err != nil {
		t.Fatalf("rotate: %v", err)
	}
	if err := service.RetireHashKey("identity-hmac-old"); err == nil {
		t.Fatal("pending unexpired challenge must block key retirement")
	}
	now = challenge.ExpiresAt
	if err := service.RetireHashKey("identity-hmac-old"); err != nil {
		t.Fatalf("expired challenge should no longer block key retirement: %v", err)
	}
	if _, err := service.CompleteEmailRegistration(CompleteRegistrationRequest{
		ChallengeID: challenge.ChallengeID,
		Secret:      challenge.Secret,
	}); err == nil {
		t.Fatal("challenge whose proof key was retired must fail closed")
	}
}

func TestIdentityHashKeyConfigurationRejectsWeakOrDuplicateKeys(t *testing.T) {
	if _, err := NewIdentityServiceWithHashKey(time.Now, "", []byte("0123456789abcdef0123456789abcdef")); err == nil {
		t.Fatal("empty key ID must be rejected")
	}
	service, err := NewIdentityServiceWithHashKey(
		time.Now,
		"identity-hmac-v1",
		[]byte("0123456789abcdef0123456789abcdef"),
	)
	if err != nil {
		t.Fatalf("new service: %v", err)
	}
	if err := service.RotateHashKey("identity-hmac-short", []byte("too-short")); err == nil {
		t.Fatal("short HMAC key must be rejected")
	}
	if err := service.RotateHashKey("identity-hmac-v1", []byte("fedcba9876543210fedcba9876543210")); err == nil {
		t.Fatal("reusing a key ID must be rejected")
	}
	if err := service.RetireHashKey("identity-hmac-v1"); err == nil {
		t.Fatal("active HMAC key must not be retired")
	}
}

func TestIdentityBindingTicketRejectsReplayWrongAccountAndExpiry(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	service := NewIdentityServiceWithClock(func() time.Time { return now })
	first := registerIdentityAccount(t, service, "first@163.com")
	second := registerIdentityAccount(t, service, "second@qq.com")

	ticket, err := service.IssueCredentialBindingTicket(first.AccountID, BindCredentialRequest{
		Provider:        "wechat_open",
		ProviderSubject: "wechat-subject-private",
		ProviderUnionID: "wechat-union-private",
	})
	if err != nil {
		t.Fatalf("issue binding ticket: %v", err)
	}
	if _, err := service.BindCredentialWithTicket(
		second.AccountID,
		second.AccountID,
		ticket.TicketID,
		ticket.Secret,
		true,
		true,
	); err == nil {
		t.Fatal("binding ticket must be account-bound")
	}
	if service.bindingTickets[ticket.TicketID].Consumed {
		t.Fatal("wrong-account attempt must not consume the rightful account's ticket")
	}
	if _, err := service.BindCredentialWithTicket(
		first.AccountID,
		first.AccountID,
		ticket.TicketID,
		ticket.Secret,
		true,
		true,
	); err != nil {
		t.Fatalf("bind rightful account: %v", err)
	}
	if _, err := service.BindCredentialWithTicket(
		first.AccountID,
		first.AccountID,
		ticket.TicketID,
		ticket.Secret,
		true,
		true,
	); err == nil {
		t.Fatal("binding ticket replay must fail")
	}

	expiring, err := service.IssueCredentialBindingTicket(first.AccountID, BindCredentialRequest{
		Provider:        "qq",
		ProviderSubject: "qq-subject-private",
	})
	if err != nil {
		t.Fatalf("issue expiring ticket: %v", err)
	}
	now = expiring.ExpiresAt
	if _, err := service.BindCredentialWithTicket(
		first.AccountID,
		first.AccountID,
		expiring.TicketID,
		expiring.Secret,
		true,
		true,
	); err == nil {
		t.Fatal("expired binding ticket must fail")
	}
}

func TestIdentityBindingTicketSurvivesRotationAndBlocksKeyRetirement(t *testing.T) {
	now := time.Date(2026, 7, 14, 0, 0, 0, 0, time.UTC)
	service, err := NewIdentityServiceWithHashKey(
		func() time.Time { return now },
		"identity-hmac-old",
		[]byte("0123456789abcdef0123456789abcdef"),
	)
	if err != nil {
		t.Fatalf("new identity service: %v", err)
	}
	account := registerIdentityAccount(t, service, "owner@126.com")
	ticket, err := service.IssueCredentialBindingTicket(account.AccountID, BindCredentialRequest{
		Provider:        "qq",
		ProviderSubject: "qq-subject-private",
	})
	if err != nil {
		t.Fatalf("issue ticket: %v", err)
	}
	if service.bindingTickets[ticket.TicketID].SecretHashKeyID != "identity-hmac-old" {
		t.Fatal("binding ticket did not record issuing HMAC key ID")
	}
	if err := service.RotateHashKey(
		"identity-hmac-new",
		[]byte("fedcba9876543210fedcba9876543210"),
	); err != nil {
		t.Fatalf("rotate HMAC key: %v", err)
	}
	if err := service.RetireHashKey("identity-hmac-old"); err == nil {
		t.Fatal("live binding ticket must block issuing-key retirement")
	}
	if _, err := service.BindCredentialWithTicket(
		account.AccountID,
		account.AccountID,
		ticket.TicketID,
		ticket.Secret,
		true,
		true,
	); err != nil {
		t.Fatalf("ticket issued before rotation must remain valid: %v", err)
	}
	if err := service.RetireHashKey("identity-hmac-old"); err != nil {
		t.Fatalf("consumed binding ticket should release old HMAC key: %v", err)
	}
}
