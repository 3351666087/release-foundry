package ashrclone

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"sync"
	"testing"
	"time"
)

type identitySequenceReader struct {
	mu   sync.Mutex
	next byte
}

func (reader *identitySequenceReader) Read(output []byte) (int, error) {
	reader.mu.Lock()
	defer reader.mu.Unlock()
	for index := range output {
		reader.next++
		output[index] = reader.next
	}
	return len(output), nil
}

func newIdentityTestService(t *testing.T) (*UnifiedIdentityService, *time.Time) {
	t.Helper()
	now := time.Date(2026, 7, 10, 10, 0, 0, 0, time.UTC)
	service, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{
		Now:            func() time.Time { return now },
		Random:         &identitySequenceReader{},
		FingerprintKey: bytes.Repeat([]byte{0x3c}, 32),
		MergePlanTTL:   5 * time.Minute,
	})
	if err != nil {
		t.Fatalf("new identity service: %v", err)
	}
	return service, &now
}

func createIdentityTestAccount(t *testing.T, service *UnifiedIdentityService, provider IdentityProvider, subject string) IdentityAccountDTO {
	t.Helper()
	account, err := service.CreateAccount(CreateIdentityAccountRequest{
		DisplayName: "Test User",
		InitialCredential: &IdentityCredentialInput{
			Kind: IdentityCredentialOAuth, Provider: provider, Identifier: subject, Verified: true,
		},
	})
	if err != nil {
		t.Fatalf("create identity account: %v", err)
	}
	return account
}

func requireIdentityCode(t *testing.T, err error, code string) {
	t.Helper()
	var domainError IdentityDomainError
	if !errors.As(err, &domainError) || domainError.Code != code {
		t.Fatalf("expected identity error %q, got %#v", code, err)
	}
}

func TestUnifiedIdentitySupportsEveryProviderAndCredentialKind(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "github-subject")

	inputs := []IdentityCredentialInput{
		{Kind: IdentityCredentialOAuth, Provider: IdentityProviderGoogle, Identifier: "google-subject", Verified: true},
		{Kind: IdentityCredentialOAuth, Provider: IdentityProviderWeChat, Identifier: "wechat-openid", Verified: true},
		{Kind: IdentityCredentialOAuth, Provider: IdentityProviderQQ, Identifier: "qq-openid", Verified: true},
		{Kind: IdentityCredentialOAuth, Provider: IdentityProviderAlipay, Identifier: "alipay-user-id", Verified: true},
		{Kind: IdentityCredentialEmail, Identifier: "USER@Example.COM", Verified: true},
		{Kind: IdentityCredentialPhone, Identifier: "+86 138-0013-8000", Verified: true},
	}
	for _, input := range inputs {
		if _, err := service.LinkCredential(account.AccountID, LinkIdentityCredentialRequest{Credential: input, ActorID: account.AccountID}); err != nil {
			t.Fatalf("link %s/%s: %v", input.Kind, input.Provider, err)
		}
	}
	updated, err := service.GetAccount(account.AccountID)
	if err != nil {
		t.Fatal(err)
	}
	if updated.CredentialCount != 7 {
		t.Fatalf("expected seven credentials, got %#v", updated)
	}
	got := map[string]bool{}
	for _, credential := range updated.Credentials {
		got[string(credential.Kind)+"/"+string(credential.Provider)] = credential.Verified && credential.CanLogin
	}
	for _, key := range []string{"oauth/github", "oauth/google", "oauth/wechat", "oauth/qq", "oauth/alipay", "email/local", "phone/local"} {
		if !got[key] {
			t.Errorf("missing verified login credential %s", key)
		}
	}
}

func TestUnifiedIdentityVerifiedOnlyLinkingAndValidation(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account, err := service.CreateAccount(CreateIdentityAccountRequest{DisplayName: "No credential"})
	if err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name  string
		input IdentityCredentialInput
		code  string
	}{
		{"unverified", IdentityCredentialInput{Kind: IdentityCredentialEmail, Identifier: "user@example.com"}, "credential_verification_required"},
		{"bad email", IdentityCredentialInput{Kind: IdentityCredentialEmail, Identifier: "not-email", Verified: true}, "invalid_email"},
		{"bad phone", IdentityCredentialInput{Kind: IdentityCredentialPhone, Identifier: "123", Verified: true}, "invalid_phone"},
		{"unsupported kind", IdentityCredentialInput{Kind: "password", Identifier: "value", Verified: true}, "unsupported_credential_kind"},
		{"unsupported oauth", IdentityCredentialInput{Kind: IdentityCredentialOAuth, Provider: "twitter", Identifier: "subject", Verified: true}, "unsupported_identity_provider"},
		{"provider on email", IdentityCredentialInput{Kind: IdentityCredentialEmail, Provider: IdentityProviderGoogle, Identifier: "user@example.com", Verified: true}, "invalid_credential_provider"},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			_, err := service.LinkCredential(account.AccountID, LinkIdentityCredentialRequest{Credential: test.input})
			requireIdentityCode(t, err, test.code)
		})
	}
}

func TestUnifiedIdentityCredentialUniquenessNormalizationAndAuthentication(t *testing.T) {
	service, now := newIdentityTestService(t)
	first := createIdentityTestAccount(t, service, IdentityProviderGitHub, "subject-first")
	second := createIdentityTestAccount(t, service, IdentityProviderGoogle, "subject-second")

	email, err := service.LinkCredential(first.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{Kind: IdentityCredentialEmail, Identifier: "Owner@Example.com", Verified: true},
	})
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.LinkCredential(first.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{Kind: IdentityCredentialEmail, Identifier: "owner@example.COM", Verified: true},
	})
	if err != nil || replay.CredentialID != email.CredentialID {
		t.Fatalf("same-account normalized link should replay: %#v %v", replay, err)
	}
	_, err = service.LinkCredential(second.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{Kind: IdentityCredentialEmail, Identifier: "OWNER@example.com", Verified: true},
	})
	requireIdentityCode(t, err, "credential_link_conflict")

	*now = now.Add(time.Minute)
	auth, err := service.Authenticate(IdentityCredentialInput{
		Kind: IdentityCredentialEmail, Identifier: "owner@example.com", Verified: true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if auth.Account.AccountID != first.AccountID || auth.Credential.CredentialID != email.CredentialID ||
		auth.Credential.LastUsedAt == nil || !auth.Credential.LastUsedAt.Equal(*now) {
		t.Fatalf("unexpected authentication: %#v", auth)
	}
	_, err = service.Authenticate(IdentityCredentialInput{Kind: IdentityCredentialEmail, Identifier: "owner@example.com"})
	requireIdentityCode(t, err, "credential_verification_required")
	_, err = service.Authenticate(IdentityCredentialInput{Kind: IdentityCredentialEmail, Identifier: "missing@example.com", Verified: true})
	if !errors.Is(err, ErrIdentityCredentialNotFound) {
		t.Fatalf("expected credential not found, got %v", err)
	}
}

func TestUnifiedIdentityCannotUnlinkLastLoginCredential(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "subject")
	first := account.Credentials[0]

	_, err := service.UnlinkCredential(account.AccountID, first.CredentialID, account.AccountID)
	requireIdentityCode(t, err, "last_login_credential")
	second, err := service.LinkCredential(account.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{Kind: IdentityCredentialPhone, Identifier: "+8613800138000", Verified: true},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.UnlinkCredential(account.AccountID, first.CredentialID, account.AccountID); err != nil {
		t.Fatal(err)
	}
	updated, err := service.GetAccount(account.AccountID)
	if err != nil {
		t.Fatal(err)
	}
	if updated.CredentialCount != 1 || updated.Credentials[0].CredentialID != second.CredentialID {
		t.Fatalf("wrong credential remained: %#v", updated.Credentials)
	}
	_, err = service.UnlinkCredential(account.AccountID, first.CredentialID, account.AccountID)
	if !errors.Is(err, ErrIdentityCredentialNotFound) {
		t.Fatalf("expected missing credential, got %v", err)
	}
}

func TestUnifiedIdentityMembershipAndConflict(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "member")
	request := IdentityMembershipRequest{TenantID: "tenant_1", ProjectID: "project_1", Role: "OWNER", ActorID: account.AccountID}
	first, err := service.AddMembership(account.AccountID, request)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := service.AddMembership(account.AccountID, request)
	if err != nil || replay.MembershipID != first.MembershipID || replay.Role != "owner" {
		t.Fatalf("membership replay failed: %#v %v", replay, err)
	}
	request.Role = "viewer"
	_, err = service.AddMembership(account.AccountID, request)
	requireIdentityCode(t, err, "membership_conflict")
	_, err = service.AddMembership(account.AccountID, IdentityMembershipRequest{Role: "owner"})
	requireIdentityCode(t, err, "invalid_membership")
}

func TestUnifiedIdentityMergePlanExecuteMovesCredentialsAndMemberships(t *testing.T) {
	service, now := newIdentityTestService(t)
	source := createIdentityTestAccount(t, service, IdentityProviderWeChat, "wechat-source")
	target := createIdentityTestAccount(t, service, IdentityProviderGoogle, "google-target")
	if _, err := service.LinkCredential(source.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{Kind: IdentityCredentialPhone, Identifier: "+8613800138000", Verified: true},
	}); err != nil {
		t.Fatal(err)
	}
	for _, item := range []struct {
		account               IdentityAccountDTO
		tenant, project, role string
	}{
		{source, "tenant", "shared", "viewer"},
		{source, "tenant", "source-only", "editor"},
		{target, "tenant", "shared", "owner"},
		{target, "tenant", "target-only", "viewer"},
	} {
		if _, err := service.AddMembership(item.account.AccountID, IdentityMembershipRequest{
			TenantID: item.tenant, ProjectID: item.project, Role: item.role, ActorID: target.AccountID,
		}); err != nil {
			t.Fatal(err)
		}
	}
	plan, err := service.PlanMerge(IdentityMergeRequest{
		SourceAccountID: source.AccountID, TargetAccountID: target.AccountID, ActorID: target.AccountID, Reason: "same human",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.CredentialsToMove) != 2 || len(plan.MembershipsToMove) != 1 || len(plan.MembershipConflicts) != 1 ||
		plan.MembershipConflicts[0].Resolution != "retain_target_membership" || plan.ResultCredentialCount != 3 ||
		plan.ResultMembershipCount != 3 || !plan.ReasonPresent {
		t.Fatalf("unexpected merge plan: %#v", plan)
	}
	*now = now.Add(time.Minute)
	result, err := service.ExecuteMerge(plan.PlanID, target.AccountID)
	if err != nil {
		t.Fatal(err)
	}
	if result.MovedCredentials != 2 || result.MovedMemberships != 1 || result.ResolvedConflicts != 1 ||
		result.TargetAccount.CredentialCount != 3 || result.TargetAccount.MembershipCount != 3 {
		t.Fatalf("unexpected merge result: %#v", result)
	}
	if _, err := service.GetAccount(source.AccountID); err == nil {
		t.Fatal("merged source should not be returned as active")
	} else {
		requireIdentityCode(t, err, "identity_account_inactive")
	}
	auth, err := service.Authenticate(IdentityCredentialInput{
		Kind: IdentityCredentialOAuth, Provider: IdentityProviderWeChat, Identifier: "wechat-source", Verified: true,
	})
	if err != nil || auth.Account.AccountID != target.AccountID {
		t.Fatalf("moved credential did not authenticate target: %#v %v", auth, err)
	}
	_, err = service.ExecuteMerge(plan.PlanID, target.AccountID)
	requireIdentityCode(t, err, "merge_plan_already_executed")
}

func TestUnifiedIdentityMergeRejectsActorExpiryAndStalePlans(t *testing.T) {
	t.Run("actor", func(t *testing.T) {
		service, _ := newIdentityTestService(t)
		source := createIdentityTestAccount(t, service, IdentityProviderGitHub, "source")
		target := createIdentityTestAccount(t, service, IdentityProviderGoogle, "target")
		plan, err := service.PlanMerge(IdentityMergeRequest{SourceAccountID: source.AccountID, TargetAccountID: target.AccountID, ActorID: "actor"})
		if err != nil {
			t.Fatal(err)
		}
		_, err = service.ExecuteMerge(plan.PlanID, "other")
		requireIdentityCode(t, err, "merge_actor_mismatch")
	})
	t.Run("expired", func(t *testing.T) {
		service, now := newIdentityTestService(t)
		source := createIdentityTestAccount(t, service, IdentityProviderGitHub, "source")
		target := createIdentityTestAccount(t, service, IdentityProviderGoogle, "target")
		plan, err := service.PlanMerge(IdentityMergeRequest{SourceAccountID: source.AccountID, TargetAccountID: target.AccountID})
		if err != nil {
			t.Fatal(err)
		}
		*now = plan.ExpiresAt
		_, err = service.ExecuteMerge(plan.PlanID, "")
		requireIdentityCode(t, err, "merge_plan_expired")
	})
	t.Run("stale", func(t *testing.T) {
		service, _ := newIdentityTestService(t)
		source := createIdentityTestAccount(t, service, IdentityProviderGitHub, "source")
		target := createIdentityTestAccount(t, service, IdentityProviderGoogle, "target")
		plan, err := service.PlanMerge(IdentityMergeRequest{SourceAccountID: source.AccountID, TargetAccountID: target.AccountID})
		if err != nil {
			t.Fatal(err)
		}
		if _, err := service.LinkCredential(source.AccountID, LinkIdentityCredentialRequest{
			Credential: IdentityCredentialInput{Kind: IdentityCredentialEmail, Identifier: "new@example.com", Verified: true},
		}); err != nil {
			t.Fatal(err)
		}
		_, err = service.ExecuteMerge(plan.PlanID, "")
		requireIdentityCode(t, err, "stale_merge_plan")
	})
}

func TestUnifiedIdentityMergePlanSameAccountAndDeduplicateMembership(t *testing.T) {
	service, _ := newIdentityTestService(t)
	source := createIdentityTestAccount(t, service, IdentityProviderGitHub, "source")
	_, err := service.PlanMerge(IdentityMergeRequest{SourceAccountID: source.AccountID, TargetAccountID: source.AccountID})
	requireIdentityCode(t, err, "same_account_merge")

	target := createIdentityTestAccount(t, service, IdentityProviderGoogle, "target")
	for _, account := range []IdentityAccountDTO{source, target} {
		if _, err := service.AddMembership(account.AccountID, IdentityMembershipRequest{TenantID: "tenant", Role: "member"}); err != nil {
			t.Fatal(err)
		}
	}
	plan, err := service.PlanMerge(IdentityMergeRequest{SourceAccountID: source.AccountID, TargetAccountID: target.AccountID})
	if err != nil {
		t.Fatal(err)
	}
	if len(plan.MembershipConflicts) != 1 || plan.MembershipConflicts[0].Resolution != "deduplicate_membership" {
		t.Fatalf("expected deduplication plan, got %#v", plan)
	}
}

func TestUnifiedIdentityPublicDTOAndAuditNeverExposeIdentifiers(t *testing.T) {
	service, _ := newIdentityTestService(t)
	const email = "secret.person@example.com"
	account, err := service.CreateAccount(CreateIdentityAccountRequest{
		DisplayName:       "Public Name",
		InitialCredential: &IdentityCredentialInput{Kind: IdentityCredentialEmail, Identifier: email, Verified: true},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.LinkCredential(account.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{Kind: IdentityCredentialOAuth, Provider: IdentityProviderGitHub, Identifier: "private-provider-subject", Verified: true},
		ActorID:    "sensitive-actor-identity",
	}); err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(struct {
		Account IdentityAccountDTO      `json:"account"`
		Audit   []IdentityAuditEventDTO `json:"audit"`
	}{account, service.AuditEvents()})
	if err != nil {
		t.Fatal(err)
	}
	text := string(payload)
	for _, forbidden := range []string{email, "private-provider-subject", "sensitive-actor-identity"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("public identity payload leaked %q: %s", forbidden, text)
		}
	}
	events := service.AuditEvents()
	if len(events) < 2 || events[len(events)-1].PreviousHash != events[len(events)-2].EventHash ||
		events[len(events)-1].EventHash == "" || !events[len(events)-1].ActorPresent {
		t.Fatalf("audit chain or actor-presence marker missing: %#v", events)
	}
	events[len(events)-1].Details["account_id"] = "mutated"
	fresh := service.AuditEvents()
	if fresh[len(fresh)-1].Details["account_id"] == "mutated" {
		t.Fatal("audit details escaped by reference")
	}
}

func TestUnifiedIdentityConcurrentCredentialClaimHasSingleOwner(t *testing.T) {
	service, _ := newIdentityTestService(t)
	first := createIdentityTestAccount(t, service, IdentityProviderGitHub, "first")
	second := createIdentityTestAccount(t, service, IdentityProviderGoogle, "second")
	accounts := []string{first.AccountID, second.AccountID}

	var wait sync.WaitGroup
	results := make(chan error, len(accounts))
	for _, accountID := range accounts {
		wait.Add(1)
		go func(accountID string) {
			defer wait.Done()
			_, err := service.LinkCredential(accountID, LinkIdentityCredentialRequest{
				Credential: IdentityCredentialInput{Kind: IdentityCredentialPhone, Identifier: "+8613800138000", Verified: true},
			})
			results <- err
		}(accountID)
	}
	wait.Wait()
	close(results)
	successes, conflicts := 0, 0
	for err := range results {
		if err == nil {
			successes++
			continue
		}
		var domainError IdentityDomainError
		if errors.As(err, &domainError) && domainError.Code == "credential_link_conflict" {
			conflicts++
			continue
		}
		t.Fatalf("unexpected concurrent result: %v", err)
	}
	if successes != 1 || conflicts != 1 {
		t.Fatalf("expected one owner and one conflict, got success=%d conflict=%d", successes, conflicts)
	}
}

func TestUnifiedIdentityConcurrentUnlinkPreservesFinalCredentialAndMemberships(t *testing.T) {
	service, _ := newIdentityTestService(t)
	account := createIdentityTestAccount(t, service, IdentityProviderGitHub, "concurrent-unlink-github")
	google, err := service.LinkCredential(account.AccountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{
			Kind:       IdentityCredentialOAuth,
			Provider:   IdentityProviderGoogle,
			Identifier: "concurrent-unlink-google",
			Verified:   true,
		},
		ActorID: account.AccountID,
	})
	if err != nil {
		t.Fatalf("link second credential: %v", err)
	}
	membership, err := service.AddMembership(account.AccountID, IdentityMembershipRequest{
		TenantID: "tenant_concurrent_unlink", ProjectID: "project_concurrent_unlink",
		Role: "owner", ActorID: account.AccountID,
	})
	if err != nil {
		t.Fatalf("add membership: %v", err)
	}

	credentialIDs := []string{account.Credentials[0].CredentialID, google.CredentialID}
	start := make(chan struct{})
	results := make(chan error, len(credentialIDs))
	var wait sync.WaitGroup
	for _, credentialID := range credentialIDs {
		wait.Add(1)
		go func(credentialID string) {
			defer wait.Done()
			<-start
			_, unlinkErr := service.UnlinkCredential(account.AccountID, credentialID, account.AccountID)
			results <- unlinkErr
		}(credentialID)
	}
	close(start)
	wait.Wait()
	close(results)

	successes, finalCredentialRejections := 0, 0
	for unlinkErr := range results {
		if unlinkErr == nil {
			successes++
			continue
		}
		var domainError IdentityDomainError
		if errors.As(unlinkErr, &domainError) && domainError.Code == "last_login_credential" {
			finalCredentialRejections++
			continue
		}
		t.Fatalf("unexpected concurrent unlink result: %v", unlinkErr)
	}
	if successes != 1 || finalCredentialRejections != 1 {
		t.Fatalf("expected one unlink and one final-credential rejection, got success=%d rejected=%d",
			successes, finalCredentialRejections)
	}

	updated, err := service.GetAccount(account.AccountID)
	if err != nil {
		t.Fatalf("get account after concurrent unlink: %v", err)
	}
	if updated.CredentialCount != 1 || !updated.Credentials[0].Verified || !updated.Credentials[0].CanLogin {
		t.Fatalf("concurrent unlink orphaned account: %#v", updated.Credentials)
	}
	if updated.MembershipCount != 1 || updated.Memberships[0].MembershipID != membership.MembershipID {
		t.Fatalf("concurrent unlink changed membership authorization: %#v", updated.Memberships)
	}
}

func TestUnifiedIdentityPublicAuditMetadataRejectsNormalizedSensitiveAliases(t *testing.T) {
	service, _ := newIdentityTestService(t)
	now := time.Unix(1_700_000_000, 0).UTC()
	service.mu.Lock()
	service.appendAuditLocked("identity.security.test", "actor", "account", "account", "success", map[string]any{
		"safe_field":   "visible",
		"TokenRef":     "secret-token-ref",
		"token-ref-id": "secret-token-ref-id",
		"nested": map[string]any{
			"revocation_outbox_id": "secret-outbox",
			"safe_nested":          "visible-nested",
		},
		"items": []any{
			map[string]any{"Provider Subject": "secret-subject", "safe_item": "visible-item"},
			map[string]any{"CLIENT.SECRET": "secret-client", "status": "ok"},
		},
	}, now)
	service.mu.Unlock()

	events := service.AuditEvents()
	if len(events) != 1 {
		t.Fatalf("expected one public audit event, got %#v", events)
	}
	encoded, err := json.Marshal(events[0].Details)
	if err != nil {
		t.Fatalf("marshal public audit details: %v", err)
	}
	public := string(encoded)
	for _, forbidden := range []string{
		"secret-token-ref", "secret-token-ref-id", "secret-outbox", "secret-subject", "secret-client",
		"TokenRef", "token-ref-id", "revocation_outbox_id", "Provider Subject", "CLIENT.SECRET",
	} {
		if strings.Contains(public, forbidden) {
			t.Fatalf("public audit metadata leaked normalized sensitive alias %q: %s", forbidden, public)
		}
	}
	for _, expected := range []string{"visible", "visible-nested", "visible-item", `"status":"ok"`} {
		if !strings.Contains(public, expected) {
			t.Fatalf("public audit metadata removed safe field %q: %s", expected, public)
		}
	}
}

func TestUnifiedIdentityAuditDetailsAreRecursivelyDetached(t *testing.T) {
	service, _ := newIdentityTestService(t)
	details := map[string]any{
		"nested": map[string]any{"safe": "original"},
		"items":  []any{map[string]any{"safe": "original"}},
	}
	service.mu.Lock()
	service.appendAuditLocked("identity.security.test", "actor", "account", "account", "success", details, time.Now().UTC())
	service.mu.Unlock()

	details["nested"].(map[string]any)["safe"] = "mutated-source"
	details["items"].([]any)[0].(map[string]any)["safe"] = "mutated-source"
	first := service.AuditEvents()
	first[0].Details["nested"].(map[string]any)["safe"] = "mutated-result"
	first[0].Details["items"].([]any)[0].(map[string]any)["safe"] = "mutated-result"

	fresh := service.AuditEvents()
	encoded, err := json.Marshal(fresh[0].Details)
	if err != nil {
		t.Fatalf("marshal detached audit details: %v", err)
	}
	if strings.Contains(string(encoded), "mutated") || strings.Count(string(encoded), "original") != 2 {
		t.Fatalf("audit details escaped recursive copy boundary: %s", encoded)
	}
}

func TestUnifiedIdentityConstructorAndMissingResources(t *testing.T) {
	_, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{FingerprintKey: []byte("short")})
	if err == nil {
		t.Fatal("expected short fingerprint key rejection")
	}
	service, _ := newIdentityTestService(t)
	if _, err := service.GetAccount("missing"); !errors.Is(err, ErrIdentityAccountNotFound) {
		t.Fatalf("expected account not found, got %v", err)
	}
	if _, err := service.ExecuteMerge("missing", "actor"); !errors.Is(err, ErrIdentityMergePlanNotFound) {
		t.Fatalf("expected merge plan not found, got %v", err)
	}
	_, err = NewUnifiedIdentityService(UnifiedIdentityServiceOptions{
		Random:         io.LimitReader(bytes.NewReader(bytes.Repeat([]byte{0x5a}, 32)), 32),
		FingerprintKey: bytes.Repeat([]byte{0x3c}, 32),
	})
	if err != nil {
		t.Fatalf("constructor should accept a bounded source for fingerprint initialization: %v", err)
	}
}
