package releasefoundry

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"
)

func newMemoryOAuthIdentityCoordinatorTest(t *testing.T) (*UnifiedIdentityService, *MemoryOAuthStore, *MemoryOAuthIdentityCoordinator) {
	t.Helper()
	now := time.Date(2026, 7, 10, 9, 0, 0, 0, time.UTC)
	identity, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{
		Now:            func() time.Time { return now },
		FingerprintKey: []byte("coordinator-test-fingerprint-key"),
	})
	if err != nil {
		t.Fatalf("new identity service: %v", err)
	}
	store := NewMemoryOAuthStore()
	coordinator, err := NewMemoryOAuthIdentityCoordinator(identity, store)
	if err != nil {
		t.Fatalf("new coordinator: %v", err)
	}
	return identity, store, coordinator
}

func coordinatedConnection(accountID, provider, subject, suffix string) OAuthConnection {
	return OAuthConnection{
		SchemaVersion:          OAuthConnectionSchemaVersion,
		Provider:               provider,
		TenantID:               "tenant",
		ProjectID:              "project",
		SessionID:              "session-" + suffix,
		UserID:                 "user-" + suffix,
		AccountID:              accountID,
		ProviderSubjectHash:    oauthProviderSubjectSHA256(provider, subject),
		ProviderSubjectPresent: true,
		TokenRef:               "token-" + suffix,
		ConnectedAt:            time.Date(2026, 7, 10, 9, 0, 0, 0, time.UTC),
	}
}

func completeCoordinatedCallback(
	t *testing.T,
	coordinator *MemoryOAuthIdentityCoordinator,
	accountID, provider, subject, suffix string,
) OAuthConnection {
	t.Helper()
	connection, err := coordinator.CompleteCallback(context.Background(), CompleteOAuthCallbackCommand{
		AccountID: accountID, Provider: provider, ProviderSubject: subject, ActorID: "actor",
		Connection: coordinatedConnection(accountID, provider, subject, suffix),
	})
	if err != nil {
		t.Fatalf("complete callback: %v", err)
	}
	return connection
}

func TestMemoryOAuthIdentityCoordinatorCommitsCredentialAndConnectionTogether(t *testing.T) {
	identity, store, coordinator := newMemoryOAuthIdentityCoordinatorTest(t)

	connection := completeCoordinatedCallback(t, coordinator, "account", "google", "google-subject", "google")
	account, err := identity.GetAccount("account")
	if err != nil {
		t.Fatalf("get account: %v", err)
	}
	if account.CredentialCount != 1 || account.Credentials[0].CredentialID != connection.CredentialID {
		t.Fatalf("credential and connection did not commit together: account=%+v connection=%+v", account, connection)
	}
	stored, err := store.GetOAuthConnection(context.Background(), OAuthSecretBinding{
		Provider: "google", TenantID: "tenant", ProjectID: "project",
		SessionID: "session-google", UserID: "user-google", AccountID: "account",
	})
	if err != nil || stored.CredentialID != account.Credentials[0].CredentialID {
		t.Fatalf("stored connection mismatch: stored=%+v err=%v", stored, err)
	}
}

func TestMemoryOAuthIdentityCoordinatorRollsBackExactNewCredentialOnConnectionConflict(t *testing.T) {
	identity, store, coordinator := newMemoryOAuthIdentityCoordinatorTest(t)
	conflictingHash := oauthProviderSubjectSHA256("google", "occupied-subject")
	store.subjectOwners["google:"+conflictingHash] = "other-account"

	connection := coordinatedConnection("account", "google", "occupied-subject", "conflict")
	_, err := coordinator.CompleteCallback(context.Background(), CompleteOAuthCallbackCommand{
		AccountID: "account", Provider: "google", ProviderSubject: "occupied-subject", ActorID: "actor",
		Connection: connection,
	})
	if err == nil {
		t.Fatal("expected provider connection ownership conflict")
	}
	if _, err := identity.GetAccount("account"); !errors.Is(err, ErrIdentityAccountNotFound) {
		t.Fatalf("new account and final new credential must be rolled back exactly, got %v", err)
	}
	if owner := store.subjectOwners["google:"+conflictingHash]; owner != "other-account" {
		t.Fatalf("existing subject owner changed during rollback: %q", owner)
	}
}

func TestMemoryOAuthIdentityCoordinatorRollbackDoesNotRemovePreexistingCredential(t *testing.T) {
	identity, _, coordinator := newMemoryOAuthIdentityCoordinatorTest(t)
	first := completeCoordinatedCallback(t, coordinator, "account", "google", "subject", "first")
	coordinator.afterIdentityMutation = func() error { return errors.New("injected connection commit failure") }

	_, err := coordinator.CompleteCallback(context.Background(), CompleteOAuthCallbackCommand{
		AccountID: "account", Provider: "google", ProviderSubject: "subject", ActorID: "actor",
		Connection: coordinatedConnection("account", "google", "subject", "second"),
	})
	if err == nil {
		t.Fatal("expected injected failure")
	}
	account, err := identity.GetAccount("account")
	if err != nil {
		t.Fatalf("get account after rollback: %v", err)
	}
	if account.CredentialCount != 1 || account.Credentials[0].CredentialID != first.CredentialID {
		t.Fatalf("rollback removed or replaced preexisting credential: %+v", account.Credentials)
	}
}

func TestMemoryOAuthIdentityCoordinatorRejectsFinalCredentialBeforeConnectionMutation(t *testing.T) {
	identity, store, coordinator := newMemoryOAuthIdentityCoordinatorTest(t)
	connection := completeCoordinatedCallback(t, coordinator, "account", "google", "subject", "only")
	binding := OAuthSecretBinding{
		Provider: "google", TenantID: "tenant", ProjectID: "project",
		SessionID: "session-only", UserID: "user-only", AccountID: "account",
	}

	_, err := coordinator.DisconnectCredential(context.Background(), DisconnectOAuthCredentialCommand{
		AccountID: "account", ActorID: "actor", Binding: binding,
	})
	if err == nil {
		t.Fatal("expected final login credential protection")
	}
	stored, getErr := store.GetOAuthConnection(context.Background(), binding)
	if getErr != nil || stored.DisconnectedAt != nil || stored.TokenRef != connection.TokenRef {
		t.Fatalf("connection changed before final-credential rejection: stored=%+v err=%v", stored, getErr)
	}
	account, getErr := identity.GetAccount("account")
	if getErr != nil || account.CredentialCount != 1 {
		t.Fatalf("canonical identity changed before preflight rejection: account=%+v err=%v", account, getErr)
	}
}

func TestMemoryOAuthIdentityCoordinatorDisconnectsOneCredentialAndPreservesMembership(t *testing.T) {
	identity, store, coordinator := newMemoryOAuthIdentityCoordinatorTest(t)
	google := completeCoordinatedCallback(t, coordinator, "account", "google", "google-subject", "google")
	completeCoordinatedCallback(t, coordinator, "account", "github", "github-subject", "github")
	if _, err := identity.AddMembership("account", IdentityMembershipRequest{
		TenantID: "tenant", ProjectID: "project", Role: "owner", ActorID: "actor",
	}); err != nil {
		t.Fatalf("add membership: %v", err)
	}
	binding := OAuthSecretBinding{
		Provider: "google", TenantID: "tenant", ProjectID: "project",
		SessionID: "session-google", UserID: "user-google", AccountID: "account",
	}
	disconnected, err := coordinator.DisconnectCredential(context.Background(), DisconnectOAuthCredentialCommand{
		AccountID: "account", ActorID: "actor", Binding: binding,
		Disconnected: time.Date(2026, 7, 10, 10, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatalf("disconnect credential: %v", err)
	}
	if disconnected.DisconnectedAt == nil || disconnected.TokenRef != "" {
		t.Fatalf("connection was not disconnected atomically: %+v", disconnected)
	}
	account, err := identity.GetAccount("account")
	if err != nil {
		t.Fatalf("get account: %v", err)
	}
	if account.CredentialCount != 1 || account.MembershipCount != 1 {
		t.Fatalf("disconnect damaged account authorization state: %+v", account)
	}
	for _, credential := range account.Credentials {
		if credential.CredentialID == google.CredentialID {
			t.Fatalf("disconnected canonical credential remains linked: %+v", credential)
		}
	}
	if _, err := store.GetOAuthConnection(context.Background(), binding); !errors.Is(err, ErrOAuthConnectionNotFound) {
		t.Fatalf("disconnected connection remained active: %v", err)
	}
}

func TestMemoryOAuthIdentityCoordinatorRestoresDisconnectSnapshotOnFailure(t *testing.T) {
	identity, store, coordinator := newMemoryOAuthIdentityCoordinatorTest(t)
	google := completeCoordinatedCallback(t, coordinator, "account", "google", "google-subject", "google")
	completeCoordinatedCallback(t, coordinator, "account", "github", "github-subject", "github")
	coordinator.afterIdentityMutation = func() error { return errors.New("injected disconnect commit failure") }
	binding := OAuthSecretBinding{
		Provider: "google", TenantID: "tenant", ProjectID: "project",
		SessionID: "session-google", UserID: "user-google", AccountID: "account",
	}

	if _, err := coordinator.DisconnectCredential(context.Background(), DisconnectOAuthCredentialCommand{
		AccountID: "account", ActorID: "actor", Binding: binding,
	}); err == nil {
		t.Fatal("expected injected disconnect failure")
	}
	account, err := identity.GetAccount("account")
	if err != nil || account.CredentialCount != 2 {
		t.Fatalf("identity snapshot was not restored: account=%+v err=%v", account, err)
	}
	found := false
	for _, credential := range account.Credentials {
		found = found || credential.CredentialID == google.CredentialID
	}
	if !found {
		t.Fatal("exact disconnected credential was not restored")
	}
	connection, err := store.GetOAuthConnection(context.Background(), binding)
	if err != nil || connection.DisconnectedAt != nil || connection.TokenRef == "" {
		t.Fatalf("connection snapshot was not restored: connection=%+v err=%v", connection, err)
	}
}

func TestMemoryOAuthIdentityCoordinatorConcurrentSubjectClaimHasOneOwner(t *testing.T) {
	identity, _, coordinator := newMemoryOAuthIdentityCoordinatorTest(t)
	const contenders = 16
	var wait sync.WaitGroup
	wait.Add(contenders)
	successes := make(chan string, contenders)
	failures := make(chan error, contenders)
	for index := 0; index < contenders; index++ {
		go func(index int) {
			defer wait.Done()
			accountID := fmt.Sprintf("account-%02d", index)
			_, err := coordinator.CompleteCallback(context.Background(), CompleteOAuthCallbackCommand{
				AccountID: accountID, Provider: "google", ProviderSubject: "shared-subject", ActorID: "actor",
				Connection: coordinatedConnection(accountID, "google", "shared-subject", fmt.Sprintf("%02d", index)),
			})
			if err != nil {
				failures <- err
				return
			}
			successes <- accountID
		}(index)
	}
	wait.Wait()
	close(successes)
	close(failures)

	if len(successes) != 1 || len(failures) != contenders-1 {
		t.Fatalf("expected one owner and %d conflicts, got successes=%d failures=%d", contenders-1, len(successes), len(failures))
	}
	for accountID := range successes {
		account, err := identity.GetAccount(accountID)
		if err != nil || account.CredentialCount != 1 {
			t.Fatalf("winning account invalid: account=%+v err=%v", account, err)
		}
	}
	for err := range failures {
		var oauthErr OAuthError
		if !errors.As(err, &oauthErr) || oauthErr.Status != 409 || oauthErr.Code != "credential_link_conflict" {
			t.Fatalf("unexpected ownership failure: %v", err)
		}
	}
}
