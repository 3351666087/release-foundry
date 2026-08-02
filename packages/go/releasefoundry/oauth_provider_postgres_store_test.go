package releasefoundry

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/lib/pq"
)

type recordingOAuthVault struct {
	putNamespace string
	putBinding   OAuthSecretBinding
	putPayload   []byte
	putRef       string
	values       map[string][]byte
	bindings     map[string]OAuthSecretBinding
	deleteCalls  []string
	deleteErr    error
}

func (vault *recordingOAuthVault) Put(
	_ context.Context,
	namespace string,
	binding OAuthSecretBinding,
	payload []byte,
) (string, error) {
	vault.putNamespace = namespace
	vault.putBinding = binding
	vault.putPayload = append([]byte(nil), payload...)
	if vault.values == nil {
		vault.values = map[string][]byte{}
	}
	if vault.bindings == nil {
		vault.bindings = map[string]OAuthSecretBinding{}
	}
	vault.values[vault.putRef] = append([]byte(nil), payload...)
	vault.bindings[vault.putRef] = binding
	return vault.putRef, nil
}

func (vault *recordingOAuthVault) Get(_ context.Context, ref string) ([]byte, error) {
	payload, ok := vault.values[ref]
	if !ok {
		return nil, errors.New("vault value not found")
	}
	return append([]byte(nil), payload...), nil
}

func (vault *recordingOAuthVault) Binding(_ context.Context, ref string) (OAuthSecretBinding, error) {
	binding, ok := vault.bindings[ref]
	if !ok {
		return OAuthSecretBinding{}, errors.New("vault binding not found")
	}
	return binding, nil
}

func (vault *recordingOAuthVault) Delete(_ context.Context, ref string) error {
	vault.deleteCalls = append(vault.deleteCalls, ref)
	if vault.deleteErr != nil {
		return vault.deleteErr
	}
	delete(vault.values, ref)
	delete(vault.bindings, ref)
	return nil
}

func TestPostgresOAuthStoreImplementsNeutralContracts(t *testing.T) {
	var store *PostgresOAuthStore
	var _ OAuthTransactionStore = store
	var _ OAuthSecretStore = store
	var _ OAuthConnectionStore = store
}

func TestPostgresOAuthStoreRejectsNonCanonicalProviderBeforeVaultOrDB(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	vault := &recordingOAuthVault{putRef: "vault:unused"}
	store, err := NewPostgresOAuthStore(db, vault)
	if err != nil {
		t.Fatal(err)
	}

	now := time.Date(2026, 7, 10, 12, 0, 0, 0, time.UTC)
	err = store.CreateOAuthTransaction(context.Background(), OAuthTransaction{
		Provider: "Google", StateHash: "state", CodeVerifier: "verifier",
		TenantID: "tenant", ProjectID: "project", SessionID: "session",
		UserID: "user", AccountID: "account", CreatedAt: now, ExpiresAt: now.Add(time.Minute),
	})
	if err == nil || !strings.Contains(err.Error(), "provider must match") {
		t.Fatalf("expected canonical provider validation error, got %v", err)
	}
	if vault.putNamespace != "" {
		t.Fatalf("vault must not be called for invalid provider, got %q", vault.putNamespace)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthStoreCreatesGoogleTransactionWithScopedMetadata(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	vault := &recordingOAuthVault{putRef: "vault:google-transaction-1"}
	store, err := NewPostgresOAuthStore(db, vault)
	if err != nil {
		t.Fatal(err)
	}

	now := time.Date(2026, 7, 10, 12, 0, 0, 0, time.UTC)
	transaction := OAuthTransaction{
		Provider: "google", StateHash: "state-hash", CodeVerifier: "verifier", Nonce: "nonce",
		TenantID: "tenant", ProjectID: "project", SessionID: "session",
		UserID: "user", AccountID: "account", CreatedAt: now, ExpiresAt: now.Add(10 * time.Minute),
	}
	organizationID, projectID := postgresOAuthScope(transaction.TenantID, transaction.ProjectID)
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs(organizationID, projectID).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec("INSERT INTO oauth_runtime_transactions").
		WithArgs(
			organizationID, projectID, "google", postgresOAuthDigest(transaction.StateHash),
			postgresOAuthBindingDigestNeutral(oauthTransactionBinding(transaction)),
			vault.putRef, now, transaction.ExpiresAt,
		).
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectCommit()

	if err := store.CreateOAuthTransaction(context.Background(), transaction); err != nil {
		t.Fatal(err)
	}
	if vault.putNamespace != "google.oauth.transaction" {
		t.Fatalf("unexpected vault namespace %q", vault.putNamespace)
	}
	if vault.putBinding.Provider != "google" {
		t.Fatalf("provider was not preserved in vault binding: %#v", vault.putBinding)
	}
	if strings.Contains(string(vault.putPayload), vault.putRef) {
		t.Fatal("transaction payload must not contain its eventual opaque reference")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthStoreDurablyRevokesBeforeDeletingVaultSecret(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	ref := "vault:google-token-1"
	vault := &recordingOAuthVault{
		putRef: ref,
		values: map[string][]byte{ref: []byte("secret-token")},
		bindings: map[string]OAuthSecretBinding{ref: {
			Provider: "google", TenantID: "tenant", ProjectID: "project",
			SessionID: "session", UserID: "user", AccountID: "account",
		}},
	}
	store, err := NewPostgresOAuthStore(db, vault)
	if err != nil {
		t.Fatal(err)
	}

	organizationID, projectID := postgresOAuthScope("tenant", "project")
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs(organizationID, projectID).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec("SELECT id FROM a1_revoke_oauth_token_ref").
		WithArgs(postgresOAuthDigest(ref), sqlmock.AnyArg()).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()
	if err := store.DeleteOAuthToken(context.Background(), ref); err != nil {
		t.Fatal(err)
	}
	if len(vault.deleteCalls) != 1 || vault.deleteCalls[0] != ref {
		t.Fatalf("expected vault deletion after durable revoke, got %#v", vault.deleteCalls)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthStoreKeepsVaultSecretWhenDurableRevokeFails(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	ref := "vault:google-token-2"
	vault := &recordingOAuthVault{
		putRef: ref,
		values: map[string][]byte{ref: []byte("secret-token")},
		bindings: map[string]OAuthSecretBinding{ref: {
			Provider: "google", TenantID: "tenant", ProjectID: "project",
			SessionID: "session", UserID: "user", AccountID: "account",
		}},
	}
	store, err := NewPostgresOAuthStore(db, vault)
	if err != nil {
		t.Fatal(err)
	}

	organizationID, projectID := postgresOAuthScope("tenant", "project")
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs(organizationID, projectID).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec("SELECT id FROM a1_revoke_oauth_token_ref").
		WithArgs(postgresOAuthDigest(ref), sqlmock.AnyArg()).
		WillReturnError(errors.New("database unavailable"))
	mock.ExpectRollback()
	err = store.DeleteOAuthToken(context.Background(), ref)
	if err == nil || !strings.Contains(err.Error(), "revoke OAuth opaque token reference") {
		t.Fatalf("expected durable revoke error, got %v", err)
	}
	if len(vault.deleteCalls) != 0 {
		t.Fatalf("vault secret was deleted before durable revoke: %#v", vault.deleteCalls)
	}
	if string(vault.values[ref]) != "secret-token" {
		t.Fatal("vault secret must remain retryable after database failure")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthStoreTreatsInvisibleTokenReferenceAsRevokeFailure(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	ref := "vault:google-token-3"
	vault := &recordingOAuthVault{
		putRef: ref,
		values: map[string][]byte{ref: []byte("secret-token")},
		bindings: map[string]OAuthSecretBinding{ref: {
			Provider: "google", TenantID: "tenant", ProjectID: "project",
			SessionID: "session", UserID: "user", AccountID: "account",
		}},
	}
	store, err := NewPostgresOAuthStore(db, vault)
	if err != nil {
		t.Fatal(err)
	}

	organizationID, projectID := postgresOAuthScope("tenant", "project")
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs(organizationID, projectID).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec("SELECT id FROM a1_revoke_oauth_token_ref").
		WithArgs(postgresOAuthDigest(ref), sqlmock.AnyArg()).
		WillReturnError(&pq.Error{Code: "P0002", Message: "oauth opaque token reference not found"})
	mock.ExpectRollback()
	err = store.DeleteOAuthToken(context.Background(), ref)
	if err == nil {
		t.Fatal("missing or RLS-invisible durable token reference must fail closed")
	}
	if len(vault.deleteCalls) != 0 {
		t.Fatalf("vault secret was deleted after no-data revoke: %#v", vault.deleteCalls)
	}
	if string(vault.values[ref]) != "secret-token" {
		t.Fatal("vault secret must remain retryable when durable reference is not visible")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthStoreReconnectSupersedesOnlyPreviousToken(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := NewPostgresOAuthStore(db, &recordingOAuthVault{})
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 10, 14, 0, 0, 0, time.UTC)
	connection := OAuthConnection{
		Provider: "google", TenantID: "tenant", ProjectID: "project",
		AccountID: "canonical-account", SessionID: "session-new", UserID: "canonical-account",
		ProviderSubjectHash: strings.Repeat("a", 64), DisplayName: "Canonical User",
		TokenRef: "vault:new-token", ConnectedAt: now,
	}
	organizationID, projectID := postgresOAuthScope(connection.TenantID, connection.ProjectID)
	newTokenRefID := "00000000-0000-0000-0000-000000000011"
	oldTokenRefID := "00000000-0000-0000-0000-000000000010"
	connectionID := "00000000-0000-0000-0000-000000000020"

	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs(organizationID, projectID).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery("FROM oauth_token_opaque_refs").
		WithArgs(organizationID, projectID, "google", postgresOAuthDigest(connection.TokenRef)).
		WillReturnRows(sqlmock.NewRows([]string{"id"}).AddRow(newTokenRefID))
	mock.ExpectQuery("FROM oauth_account_connections").
		WithArgs(organizationID, projectID, "google", connection.AccountID).
		WillReturnRows(sqlmock.NewRows([]string{"id", "token_ref_id"}).
			AddRow(connectionID, oldTokenRefID))
	mock.ExpectQuery("INSERT INTO oauth_account_connections").
		WithArgs(
			organizationID, projectID, "google", connection.AccountID, connection.SessionID,
			connection.UserID, postgresOAuthBindingDigestNeutral(oauthConnectionBinding(connection)),
			connection.ProviderSubjectHash, connection.DisplayName, sqlmock.AnyArg(), false,
			newTokenRefID, now,
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"id", "account_id", "session_id", "user_id", "provider_subject_digest",
			"provider_login", "email_present", "token_ref_id", "connected_at", "disconnected_at",
		}).AddRow(
			connectionID, connection.AccountID, connection.SessionID, connection.UserID,
			connection.ProviderSubjectHash, connection.DisplayName, false, newTokenRefID, now, nil,
		))
	mock.ExpectExec("UPDATE oauth_token_opaque_refs").
		WithArgs(organizationID, projectID, oldTokenRefID, "google", now, connectionID).
		WillReturnResult(sqlmock.NewResult(0, 2))
	mock.ExpectCommit()

	result, err := store.UpsertOAuthConnection(context.Background(), connection)
	if err != nil {
		t.Fatal(err)
	}
	if result.AccountID != connection.AccountID || result.TokenRef != connection.TokenRef ||
		result.SessionID != connection.SessionID {
		t.Fatalf("reconnect changed canonical identity or new token binding: %#v", result)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestOAuthRuntimeMigrationSecurityInvariants(t *testing.T) {
	migration := readOAuthMigration(t, "007_a1_oauth_runtime_store.sql")
	required := []string{
		"ALTER TABLE oauth_runtime_transactions FORCE ROW LEVEL SECURITY",
		"ALTER TABLE oauth_replay_ledger FORCE ROW LEVEL SECURITY",
		"ALTER TABLE oauth_token_opaque_refs FORCE ROW LEVEL SECURITY",
		"ALTER TABLE oauth_account_connections FORCE ROW LEVEL SECURITY",
		"ALTER TABLE oauth_revocation_outbox FORCE ROW LEVEL SECURITY",
		"ALTER TABLE oauth_runtime_audit FORCE ROW LEVEL SECURITY",
		"CREATE TRIGGER oauth_replay_ledger_append_only",
		"CREATE TRIGGER oauth_runtime_audit_append_only",
		"UNIQUE (provider, state_digest)",
		"UNIQUE (provider, replay_kind, value_digest)",
		"CHECK (a1_oauth_reference_only(transaction_ref))",
		"CHECK (a1_oauth_reference_only(opaque_ref))",
		"PERFORM a1_assert_role_nobypassrls(session_user)",
		"REVOKE ALL ON FUNCTION a1_consume_oauth_runtime_transaction",
		"REVOKE ALL ON FUNCTION a1_revoke_oauth_token_ref",
	}
	for _, invariant := range required {
		if !strings.Contains(migration, invariant) {
			t.Errorf("migration 007 is missing security invariant %q", invariant)
		}
	}

	for _, forbiddenColumn := range []string{
		"access_token TEXT", "refresh_token TEXT", "id_token TEXT",
		"authorization_code TEXT", "code_verifier TEXT", "client_secret TEXT",
	} {
		if strings.Contains(strings.ToLower(migration), strings.ToLower(forbiddenColumn)) {
			t.Errorf("migration 007 contains forbidden raw-secret column %q", forbiddenColumn)
		}
	}
}

func TestOAuthRevocationMigrationFencesReclaimAndProtectsReconnect(t *testing.T) {
	migration := readOAuthMigration(t, "010_a1_identity_revocation_outbox.sql")
	required := []string{
		"FOR UPDATE SKIP LOCKED",
		"target.status = 'leased' AND target.lease_expires_at <= p_now",
		"lease_generation = target.lease_generation + 1",
		"target.lease_generation <> p_lease_generation",
		"target.lease_expires_at <= p_now",
		"AND token_ref_id = target.token_ref_id",
		"AND status = 'revocation_pending'",
	}
	for _, invariant := range required {
		if !strings.Contains(migration, invariant) {
			t.Errorf("migration 010 is missing lease/reconnect invariant %q", invariant)
		}
	}
}

func TestOAuthLifecycleMigrationRejectsSecretMetadata(t *testing.T) {
	migration := readOAuthMigration(t, "006_a1_oauth_lifecycle.sql")
	for _, key := range []string{
		"'accesstoken'", "'refreshtoken'", "'idtoken'", "'authorizationcode'",
		"'codeverifier'", "'clientsecret'", "'state'", "'nonce'", "'password'", "'cookie'",
	} {
		if !strings.Contains(migration, key) {
			t.Errorf("migration 006 public metadata guard does not reject %s", key)
		}
	}
	if !strings.Contains(migration, "a1_oauth_reference_only") {
		t.Fatal("migration 006 must constrain secret material to opaque references")
	}
}

func readOAuthMigration(t *testing.T, name string) string {
	t.Helper()
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test file path")
	}
	path := filepath.Join(filepath.Dir(currentFile), "..", "..", "..", "services", "api", "migrations", name)
	content, err := os.ReadFile(filepath.Clean(path))
	if err != nil {
		t.Fatalf("read migration %s: %v", name, err)
	}
	return string(content)
}
