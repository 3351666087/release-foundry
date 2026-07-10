package ashrclone

import (
	"context"
	"errors"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/lib/pq"
)

type revocationWorkerStore struct {
	tasks                 []OAuthRevocationTask
	providerCheckpoints   int
	vaultCheckpoints      int
	completions           int
	retries               int
	deadLetter            bool
	providerCheckpointErr error
	vaultCheckpointErr    error
}

func (store *revocationWorkerStore) ClaimOAuthRevocations(
	context.Context, string, string, string, int, time.Duration, time.Time,
) ([]OAuthRevocationTask, error) {
	return append([]OAuthRevocationTask(nil), store.tasks...), nil
}

func (store *revocationWorkerStore) MarkOAuthProviderRevoked(
	_ context.Context, _ OAuthRevocationTask, _ time.Time,
) error {
	store.providerCheckpoints++
	return store.providerCheckpointErr
}

func (store *revocationWorkerStore) MarkOAuthVaultDeleted(
	_ context.Context, _ OAuthRevocationTask, _ time.Time,
) error {
	store.vaultCheckpoints++
	return store.vaultCheckpointErr
}

func (store *revocationWorkerStore) CompleteOAuthRevocation(
	context.Context, OAuthRevocationTask, time.Time,
) error {
	store.completions++
	return nil
}

func (store *revocationWorkerStore) RetryOAuthRevocation(
	context.Context, OAuthRevocationTask, string, time.Duration, time.Duration, time.Time,
) (bool, time.Time, error) {
	store.retries++
	return store.deadLetter, time.Time{}, nil
}

type revocationWorkerVault struct {
	payload     []byte
	getCalls    int
	deleteCalls int
	deleteErr   error
}

func (*revocationWorkerVault) Put(context.Context, string, OAuthSecretBinding, []byte) (string, error) {
	return "", errors.New("not implemented")
}
func (vault *revocationWorkerVault) Get(context.Context, string) ([]byte, error) {
	vault.getCalls++
	return append([]byte(nil), vault.payload...), nil
}
func (*revocationWorkerVault) Binding(context.Context, string) (OAuthSecretBinding, error) {
	return OAuthSecretBinding{}, errors.New("not implemented")
}
func (vault *revocationWorkerVault) Delete(context.Context, string) error {
	vault.deleteCalls++
	return vault.deleteErr
}

type revocationWorkerProvider struct {
	revokeCalls int
	revokeErr   error
}

func (*revocationWorkerProvider) Name() string          { return "google" }
func (*revocationWorkerProvider) SchemaVersion() string { return "test" }
func (*revocationWorkerProvider) ExactScopes() []string { return nil }
func (*revocationWorkerProvider) AuthorizationURL(OAuthAuthorizationRequest) (string, error) {
	return "", errors.New("not implemented")
}
func (*revocationWorkerProvider) ExchangeCode(context.Context, OAuthCodeExchangeRequest) (OAuthTokenSet, error) {
	return OAuthTokenSet{}, errors.New("not implemented")
}
func (*revocationWorkerProvider) ResolveIdentity(context.Context, OAuthIdentityRequest) (OAuthProviderIdentity, error) {
	return OAuthProviderIdentity{}, errors.New("not implemented")
}
func (provider *revocationWorkerProvider) RevokeToken(
	context.Context, OAuthClientCredentials, string,
) error {
	provider.revokeCalls++
	return provider.revokeErr
}

type revocationWorkerResolver struct{ provider OAuthProviderAdapter }

func (resolver revocationWorkerResolver) OAuthRevocationProvider(
	context.Context, string,
) (OAuthProviderAdapter, error) {
	return resolver.provider, nil
}

func revocationTask() OAuthRevocationTask {
	return OAuthRevocationTask{
		ID: "outbox", TenantID: "tenant", ProjectID: "project",
		Provider: "google", ConnectionID: "connection", TokenRefID: "token-ref",
		OpaqueRef: "vault:token", OperationKind: "provider_revoke_and_cleanup",
		ReasonCode: "disconnect", Attempt: 1, MaxAttempts: 12,
		LeaseOwner: "worker", LeaseGeneration: 1,
		LeaseExpiresAt: time.Date(2026, 7, 10, 13, 1, 0, 0, time.UTC),
	}
}

func newRevocationWorker(
	t *testing.T,
	store *revocationWorkerStore,
	vault *revocationWorkerVault,
	provider *revocationWorkerProvider,
) *OAuthRevocationWorker {
	t.Helper()
	worker, err := NewOAuthRevocationWorker(OAuthRevocationWorkerOptions{
		Store: store, Vault: vault,
		Providers:   revocationWorkerResolver{provider: provider},
		Credentials: oauthTestCredentials{}, LeaseOwner: "worker",
		Now: func() time.Time {
			return time.Date(2026, 7, 10, 13, 0, 0, 0, time.UTC)
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	return worker
}

func TestOAuthRevocationWorkerCompletesDurablePhases(t *testing.T) {
	store := &revocationWorkerStore{tasks: []OAuthRevocationTask{revocationTask()}}
	vault := &revocationWorkerVault{payload: []byte("provider-token")}
	provider := &revocationWorkerProvider{}

	result, err := newRevocationWorker(t, store, vault, provider).
		ProcessBatch(context.Background(), "tenant", "project", 10)
	if err != nil {
		t.Fatal(err)
	}
	if result.Delivered != 1 || provider.revokeCalls != 1 || vault.deleteCalls != 1 ||
		store.providerCheckpoints != 1 || store.vaultCheckpoints != 1 || store.completions != 1 {
		t.Fatalf("unexpected durable phase result: %#v store=%#v provider=%#v vault=%#v",
			result, store, provider, vault)
	}
}

func TestOAuthRevocationWorkerResumesAfterProviderCheckpoint(t *testing.T) {
	task := revocationTask()
	checkpoint := time.Date(2026, 7, 10, 12, 59, 0, 0, time.UTC)
	task.ProviderRevokedAt = &checkpoint
	store := &revocationWorkerStore{tasks: []OAuthRevocationTask{task}}
	vault := &revocationWorkerVault{}
	provider := &revocationWorkerProvider{}

	result, err := newRevocationWorker(t, store, vault, provider).
		ProcessBatch(context.Background(), "tenant", "project", 10)
	if err != nil {
		t.Fatal(err)
	}
	if result.Delivered != 1 || provider.revokeCalls != 0 || vault.getCalls != 0 ||
		vault.deleteCalls != 1 || store.vaultCheckpoints != 1 || store.completions != 1 {
		t.Fatalf("provider checkpoint was not resumed safely: result=%#v store=%#v provider=%#v vault=%#v",
			result, store, provider, vault)
	}
}

func TestOAuthRevocationWorkerResumesAfterVaultCheckpoint(t *testing.T) {
	task := revocationTask()
	checkpoint := time.Date(2026, 7, 10, 12, 59, 0, 0, time.UTC)
	task.ProviderRevokedAt = &checkpoint
	task.VaultDeletedAt = &checkpoint
	store := &revocationWorkerStore{tasks: []OAuthRevocationTask{task}}
	vault := &revocationWorkerVault{}
	provider := &revocationWorkerProvider{}

	result, err := newRevocationWorker(t, store, vault, provider).
		ProcessBatch(context.Background(), "tenant", "project", 10)
	if err != nil {
		t.Fatal(err)
	}
	if result.Delivered != 1 || provider.revokeCalls != 0 || vault.getCalls != 0 ||
		vault.deleteCalls != 0 || store.completions != 1 {
		t.Fatalf("vault checkpoint was not resumed safely: result=%#v store=%#v provider=%#v vault=%#v",
			result, store, provider, vault)
	}
}

func TestOAuthRevocationWorkerRetriesAndDeadLettersProviderFailure(t *testing.T) {
	store := &revocationWorkerStore{
		tasks:      []OAuthRevocationTask{revocationTask()},
		deadLetter: true,
	}
	vault := &revocationWorkerVault{payload: []byte("provider-token")}
	provider := &revocationWorkerProvider{revokeErr: errors.New("upstream unavailable")}

	result, err := newRevocationWorker(t, store, vault, provider).
		ProcessBatch(context.Background(), "tenant", "project", 10)
	if err != nil {
		t.Fatal(err)
	}
	if result.DeadLettered != 1 || store.retries != 1 || vault.deleteCalls != 0 ||
		store.completions != 0 {
		t.Fatalf("provider failure did not dead-letter safely: result=%#v store=%#v vault=%#v",
			result, store, vault)
	}
}

func TestOAuthRevocationBackoffCaps(t *testing.T) {
	if got := oauthRevocationBackoff(1, time.Second, time.Minute); got != time.Second {
		t.Fatalf("first backoff = %s", got)
	}
	if got := oauthRevocationBackoff(20, time.Second, time.Minute); got != time.Minute {
		t.Fatalf("capped backoff = %s", got)
	}
}

func TestPostgresOAuthRevocationClaimReturnsFencedLease(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := NewPostgresOAuthRevocationOutboxStore(db)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 10, 13, 0, 0, 0, time.UTC)
	expiresAt := now.Add(time.Minute)
	organizationID, projectID := postgresOAuthScope("tenant", "project")
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs(organizationID, projectID).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery(regexp.QuoteMeta("FROM a1_claim_identity_revocation_outbox(")).
		WithArgs(organizationID, projectID, "worker-2", 10, 60, now).
		WillReturnRows(sqlmock.NewRows([]string{
			"outbox_id", "organization_id", "project_id", "provider", "connection_id",
			"token_ref_id", "opaque_ref", "operation_kind", "reason_code", "attempts",
			"max_attempts", "lease_owner", "lease_generation", "lease_expires_at",
			"provider_revoked_at", "vault_deleted_at",
		}).AddRow(
			"outbox-1", organizationID, projectID, "google", "connection-1",
			"token-ref-1", "vault:token-1", "provider_revoke_and_cleanup", "superseded", 2,
			12, "worker-2", int64(7), expiresAt, nil, nil,
		))
	mock.ExpectCommit()

	tasks, err := store.ClaimOAuthRevocations(
		context.Background(), "tenant", "project", "worker-2", 10, time.Minute, now,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(tasks) != 1 || tasks[0].LeaseGeneration != 7 ||
		tasks[0].LeaseOwner != "worker-2" || !tasks[0].LeaseExpiresAt.Equal(expiresAt) {
		t.Fatalf("claim did not preserve fenced lease: %#v", tasks)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthRevocationTransitionRejectsLostLeaseGeneration(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := NewPostgresOAuthRevocationOutboxStore(db)
	if err != nil {
		t.Fatal(err)
	}
	task := revocationTask()
	task.LeaseGeneration = 41
	now := time.Date(2026, 7, 10, 13, 0, 30, 0, time.UTC)
	organizationID, projectID := postgresOAuthScope(task.TenantID, task.ProjectID)
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs(organizationID, projectID).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec("a1_complete_identity_revocation_outbox").
		WithArgs(organizationID, projectID, task.ID, task.LeaseOwner, int64(41), now).
		WillReturnError(&pq.Error{Code: "40001", Message: "oauth revocation lease lost"})
	mock.ExpectRollback()

	err = store.CompleteOAuthRevocation(context.Background(), task, now)
	if err == nil || !strings.Contains(err.Error(), "lease lost during complete") {
		t.Fatalf("stale lease generation did not fail as lease loss: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
