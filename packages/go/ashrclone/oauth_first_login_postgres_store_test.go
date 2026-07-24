package ashrclone

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
)

type oauthFirstLoginStoreVault struct {
	mu        sync.Mutex
	ref       string
	namespace string
	binding   OAuthSecretBinding
	payload   []byte
	deletes   int
}

func (vault *oauthFirstLoginStoreVault) Put(_ context.Context, namespace string, binding OAuthSecretBinding, payload []byte) (string, error) {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	vault.namespace = namespace
	vault.binding = binding
	vault.payload = append([]byte(nil), payload...)
	return vault.ref, nil
}
func (vault *oauthFirstLoginStoreVault) Get(context.Context, string) ([]byte, error) {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	return append([]byte(nil), vault.payload...), nil
}
func (vault *oauthFirstLoginStoreVault) Binding(context.Context, string) (OAuthSecretBinding, error) {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	return vault.binding, nil
}
func (vault *oauthFirstLoginStoreVault) Delete(context.Context, string) error {
	vault.mu.Lock()
	defer vault.mu.Unlock()
	vault.deletes++
	return nil
}

func oauthFirstLoginStoreTestTransaction(now time.Time) OAuthFirstLoginTransaction {
	return OAuthFirstLoginTransaction{
		Provider: "github", Purpose: OAuthPurposeFirstLogin,
		StateHash: "state-hash-fixture", CodeVerifier: "pkce-verifier-fixture", Nonce: "nonce-fixture",
		IntentID:       "ofli_intent-fixture",
		OrganizationID: "11111111-1111-4111-8111-111111111111",
		ProjectID:      "22222222-2222-4222-8222-222222222222",
		CreatedAt:      now, ExpiresAt: now.Add(10 * time.Minute),
	}
}

func TestPostgresOAuthFirstLoginStorePersistsOnlyDigestAndOpaqueReference(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	vault := &oauthFirstLoginStoreVault{ref: "vault:oauth/first-login-transaction-1"}
	store, err := NewPostgresOAuthFirstLoginStore(db, vault)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 24, 2, 0, 0, 0, time.UTC)
	transaction := oauthFirstLoginStoreTestTransaction(now)
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").WithArgs(transaction.OrganizationID, transaction.ProjectID).WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec("INSERT INTO oauth_runtime_transactions").WithArgs(
		transaction.OrganizationID, transaction.ProjectID, transaction.Provider,
		postgresOAuthDigest(transaction.StateHash), sqlmock.AnyArg(), vault.ref,
		transaction.CreatedAt, transaction.ExpiresAt,
	).WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectCommit()
	if err := store.CreateOAuthFirstLoginTransaction(context.Background(), transaction); err != nil {
		t.Fatal(err)
	}
	if vault.namespace != "github.oauth.first_login.transaction.v1" {
		t.Fatalf("first-login transaction used an overlapping vault namespace %q", vault.namespace)
	}
	if strings.Contains(string(vault.payload), "access_token") {
		t.Fatal("first-login transaction envelope unexpectedly contains a provider token")
	}
	var envelope oauthFirstLoginVaultEnvelope
	if err := json.Unmarshal(vault.payload, &envelope); err != nil {
		t.Fatal(err)
	}
	if envelope.SchemaVersion != oauthFirstLoginVaultSchemaVersion || envelope.Kind != oauthFirstLoginVaultTransactionKind || envelope.Transaction == nil || *envelope.Transaction != transaction {
		t.Fatalf("first-login transaction vault envelope is invalid: %#v", envelope)
	}
	if vault.binding.Provider != "github" || vault.binding.TenantID != transaction.OrganizationID || vault.binding.ProjectID != transaction.ProjectID || vault.binding.SessionID != "oauth_first_login_transaction:"+transaction.IntentID || vault.binding.UserID != vault.binding.SessionID || vault.binding.AccountID != vault.binding.SessionID {
		t.Fatalf("first-login transaction vault binding is invalid: %#v", vault.binding)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthFirstLoginStoreConsumesOneTimeBoundEnvelope(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	now := time.Date(2026, 7, 24, 2, 15, 0, 0, time.UTC)
	transaction := oauthFirstLoginStoreTestTransaction(now.Add(-time.Minute))
	payload, err := json.Marshal(newOAuthFirstLoginVaultEnvelope(transaction))
	if err != nil {
		t.Fatal(err)
	}
	binding := oauthFirstLoginTransactionBinding(transaction)
	vault := &oauthFirstLoginStoreVault{ref: "vault:oauth/first-login-transaction-2", payload: payload, binding: binding}
	store, err := NewPostgresOAuthFirstLoginStore(db, vault)
	if err != nil {
		t.Fatal(err)
	}
	mock.ExpectQuery("a1_consume_oauth_runtime_transaction").WithArgs(
		"github", postgresOAuthDigest(transaction.StateHash), now,
	).WillReturnRows(sqlmock.NewRows([]string{"transaction_ref", "expires_at", "status"}).AddRow(vault.ref, transaction.ExpiresAt, "consumed"))
	consumed, err := store.ConsumeOAuthFirstLoginTransaction(context.Background(), "github", transaction.StateHash, now)
	if err != nil {
		t.Fatal(err)
	}
	if consumed != transaction || vault.deletes != 1 {
		t.Fatalf("first-login transaction was not consumed exactly once: transaction=%#v deletes=%d", consumed, vault.deletes)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthFirstLoginStoreWritesTokenOnlyToVaultBeforeCoordinator(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	vault := &oauthFirstLoginStoreVault{ref: "vault:oauth/first-login-token-1"}
	store, err := NewPostgresOAuthFirstLoginStore(db, vault)
	if err != nil {
		t.Fatal(err)
	}
	handle := "oauth_first_login:ofli_intent-fixture"
	binding := OAuthSecretBinding{
		Provider: "google", TenantID: "11111111-1111-4111-8111-111111111111",
		ProjectID: "22222222-2222-4222-8222-222222222222",
		SessionID: handle, UserID: handle, AccountID: handle,
	}
	ref, err := store.PutOAuthToken(context.Background(), binding, "provider-access-token-fixture")
	if err != nil || ref != vault.ref {
		t.Fatalf("first-login token vault put failed: ref=%q err=%v", ref, err)
	}
	if vault.namespace != "google.oauth.first_login.access_token.v1" || string(vault.payload) != "provider-access-token-fixture" {
		t.Fatalf("first-login token used an invalid namespace or payload")
	}
	// No SQL expectation is installed. Any premature oauth_token_opaque_refs write
	// would fail this call before migration 026 can remain the sole authority.
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthFirstLoginStoreRejectsEnvelopeOrBindingMismatch(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	now := time.Date(2026, 7, 24, 2, 30, 0, 0, time.UTC)
	transaction := oauthFirstLoginStoreTestTransaction(now.Add(-time.Minute))
	payload, err := json.Marshal(newOAuthFirstLoginVaultEnvelope(transaction))
	if err != nil {
		t.Fatal(err)
	}
	binding := oauthFirstLoginTransactionBinding(transaction)
	binding.ProjectID = "33333333-3333-4333-8333-333333333333"
	vault := &oauthFirstLoginStoreVault{ref: "vault:oauth/first-login-transaction-3", payload: payload, binding: binding}
	store, err := NewPostgresOAuthFirstLoginStore(db, vault)
	if err != nil {
		t.Fatal(err)
	}
	mock.ExpectQuery("a1_consume_oauth_runtime_transaction").WithArgs("github", postgresOAuthDigest(transaction.StateHash), now).WillReturnRows(
		sqlmock.NewRows([]string{"transaction_ref", "expires_at", "status"}).AddRow(vault.ref, transaction.ExpiresAt, "consumed"),
	)
	_, err = store.ConsumeOAuthFirstLoginTransaction(context.Background(), "github", transaction.StateHash, now)
	if err == nil || errors.Is(err, sql.ErrNoRows) || strings.Contains(err.Error(), transaction.StateHash) || strings.Contains(err.Error(), transaction.CodeVerifier) || strings.Contains(err.Error(), transaction.Nonce) {
		t.Fatalf("first-login vault binding mismatch was accepted or leaked: %v", err)
	}
}
