package ashrclone

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"
)

const (
	oauthFirstLoginVaultSchemaVersion   = "ashr.oauth_first_login.vault.v1"
	oauthFirstLoginVaultTransactionKind = "oauth_first_login_transaction"
)

type oauthFirstLoginVaultEnvelope struct {
	SchemaVersion string                      `json:"schema_version"`
	Kind          string                      `json:"kind"`
	Transaction   *OAuthFirstLoginTransaction `json:"transaction,omitempty"`
}

func newOAuthFirstLoginVaultEnvelope(
	transaction OAuthFirstLoginTransaction,
) oauthFirstLoginVaultEnvelope {
	copyTransaction := transaction
	return oauthFirstLoginVaultEnvelope{
		SchemaVersion: oauthFirstLoginVaultSchemaVersion,
		Kind:          oauthFirstLoginVaultTransactionKind,
		Transaction:   &copyTransaction,
	}
}

// PostgresOAuthFirstLoginStore intentionally differs from PostgresOAuthStore:
// migration 026 is the sole database authority that creates the durable token
// reference during canonical-account completion. Before that transaction,
// provider tokens exist only in the external opaque vault.
type PostgresOAuthFirstLoginStore struct {
	db    *sql.DB
	vault OAuthOpaqueVault
}

func NewPostgresOAuthFirstLoginStore(
	db *sql.DB,
	vault OAuthOpaqueVault,
) (*PostgresOAuthFirstLoginStore, error) {
	if db == nil {
		return nil, fmt.Errorf("OAuth first-login postgres db is required")
	}
	if vault == nil {
		return nil, fmt.Errorf("OAuth first-login opaque vault is required")
	}
	return &PostgresOAuthFirstLoginStore{db: db, vault: vault}, nil
}

func (store *PostgresOAuthFirstLoginStore) CreateOAuthFirstLoginTransaction(
	ctx context.Context,
	transaction OAuthFirstLoginTransaction,
) error {
	transaction.CreatedAt = transaction.CreatedAt.UTC().Truncate(time.Microsecond)
	transaction.ExpiresAt = transaction.ExpiresAt.UTC().Truncate(time.Microsecond)
	if ctx == nil || validatePostgresOAuthFirstLoginTransaction(transaction) != nil {
		return errors.New("OAuth first-login transaction is invalid")
	}
	binding := oauthFirstLoginTransactionBinding(transaction)
	payload, err := json.Marshal(newOAuthFirstLoginVaultEnvelope(transaction))
	if err != nil {
		return errors.New("encode OAuth first-login transaction failed")
	}
	defer clear(payload)
	ref, err := store.vault.Put(
		ctx,
		transaction.Provider+".oauth.first_login.transaction.v1",
		binding,
		payload,
	)
	if err != nil {
		return errors.New("vault OAuth first-login transaction failed")
	}
	if !isOAuthOpaqueReference(ref) {
		_ = store.vault.Delete(ctx, ref)
		return errors.New("OAuth first-login vault returned an invalid opaque reference")
	}

	tx, err := store.db.BeginTx(ctx, nil)
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		return fmt.Errorf("begin OAuth first-login transaction insert: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	if err := setPostgresOAuthScopeNeutral(
		ctx, tx, transaction.OrganizationID, transaction.ProjectID,
	); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return err
	}
	var created bool
	err = tx.QueryRowContext(ctx, `
SELECT a1_create_oauth_runtime_transaction(
  $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8
)
`, transaction.OrganizationID, transaction.ProjectID, transaction.Provider,
		postgresOAuthDigest(transaction.StateHash),
		postgresOAuthBindingDigestNeutral(binding), ref,
		transaction.CreatedAt, transaction.ExpiresAt).Scan(&created)
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		if postgresOAuthUniqueViolation(err) {
			return errors.New("OAuth first-login state collision")
		}
		return fmt.Errorf("insert OAuth first-login runtime transaction: %w", err)
	}
	if !created {
		_ = store.vault.Delete(ctx, ref)
		return errors.New("OAuth first-login runtime transaction was not created")
	}
	if err := tx.Commit(); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return fmt.Errorf("commit OAuth first-login runtime transaction: %w", err)
	}
	return nil
}

func (store *PostgresOAuthFirstLoginStore) ConsumeOAuthFirstLoginTransaction(
	ctx context.Context,
	provider string,
	stateHash string,
	now time.Time,
) (OAuthFirstLoginTransaction, error) {
	provider, err := normalizeOAuthPostgresProvider(provider)
	if err != nil || ctx == nil || !validOAuthFirstLoginHandle(stateHash, 128) || now.IsZero() {
		return OAuthFirstLoginTransaction{}, errors.New("OAuth first-login transaction lookup is invalid")
	}
	var ref string
	var expiresAt time.Time
	var status string
	err = store.db.QueryRowContext(ctx, `
SELECT transaction_ref, expires_at, status
  FROM a1_consume_oauth_runtime_transaction($1, $2, $3)
`, provider, postgresOAuthDigest(stateHash), now.UTC()).Scan(&ref, &expiresAt, &status)
	if err != nil {
		return OAuthFirstLoginTransaction{}, mapPostgresOAuthFirstLoginTransactionError(provider, err)
	}
	if status != "consumed" || !now.UTC().Before(expiresAt.UTC()) || !isOAuthOpaqueReference(ref) {
		if status == "expired" || !now.UTC().Before(expiresAt.UTC()) {
			return OAuthFirstLoginTransaction{}, ErrOAuthTransactionExpired
		}
		return OAuthFirstLoginTransaction{}, errors.New("OAuth first-login transaction result is invalid")
	}
	payload, err := store.vault.Get(ctx, ref)
	if err != nil {
		return OAuthFirstLoginTransaction{}, errors.New("load OAuth first-login transaction from vault failed")
	}
	defer clear(payload)
	binding, err := store.vault.Binding(ctx, ref)
	if err != nil {
		return OAuthFirstLoginTransaction{}, errors.New("resolve OAuth first-login transaction binding failed")
	}
	var envelope oauthFirstLoginVaultEnvelope
	if err := decodeStrictOAuthFirstLoginVaultEnvelope(payload, &envelope); err != nil ||
		envelope.SchemaVersion != oauthFirstLoginVaultSchemaVersion ||
		envelope.Kind != oauthFirstLoginVaultTransactionKind || envelope.Transaction == nil {
		return OAuthFirstLoginTransaction{}, errors.New("OAuth first-login transaction envelope is invalid")
	}
	transaction := *envelope.Transaction
	if validatePostgresOAuthFirstLoginTransaction(transaction) != nil ||
		transaction.Provider != provider || transaction.StateHash != stateHash ||
		!transaction.ExpiresAt.Equal(expiresAt.UTC()) ||
		binding != oauthFirstLoginTransactionBinding(transaction) {
		return OAuthFirstLoginTransaction{}, errors.New("OAuth first-login transaction vault binding mismatch")
	}
	if err := store.vault.Delete(ctx, ref); err != nil {
		return OAuthFirstLoginTransaction{}, errors.New("delete consumed OAuth first-login transaction from vault failed")
	}
	return transaction, nil
}

func (store *PostgresOAuthFirstLoginStore) PutOAuthToken(
	ctx context.Context,
	binding OAuthSecretBinding,
	token string,
) (string, error) {
	if ctx == nil || validatePostgresOAuthFirstLoginTokenBinding(binding) != nil ||
		token == "" || token != strings.TrimSpace(token) ||
		len(token) > maxOAuthOpaqueVaultSecretBytes {
		return "", errors.New("OAuth first-login token request is invalid")
	}
	ref, err := store.vault.Put(
		ctx,
		binding.Provider+".oauth.first_login.access_token.v1",
		binding,
		[]byte(token),
	)
	if err != nil {
		return "", errors.New("vault OAuth first-login token failed")
	}
	if !isOAuthOpaqueReference(ref) {
		_ = store.vault.Delete(ctx, ref)
		return "", errors.New("OAuth first-login vault returned an invalid opaque reference")
	}
	return ref, nil
}

func (store *PostgresOAuthFirstLoginStore) GetOAuthToken(
	ctx context.Context,
	ref string,
) (string, error) {
	if ctx == nil || !isOAuthOpaqueReference(ref) {
		return "", errors.New("OAuth first-login token reference is invalid")
	}
	payload, err := store.vault.Get(ctx, ref)
	if err != nil {
		return "", errors.New("load OAuth first-login token from vault failed")
	}
	defer clear(payload)
	if len(payload) < 1 || len(payload) > maxOAuthOpaqueVaultSecretBytes {
		return "", errors.New("OAuth first-login token payload is invalid")
	}
	return string(payload), nil
}

func (store *PostgresOAuthFirstLoginStore) DeleteOAuthToken(
	ctx context.Context,
	ref string,
) error {
	if ctx == nil || !isOAuthOpaqueReference(ref) {
		return errors.New("OAuth first-login token reference is invalid")
	}
	if err := store.vault.Delete(ctx, ref); err != nil {
		return errors.New("delete OAuth first-login token from vault failed")
	}
	return nil
}

func validatePostgresOAuthFirstLoginTransaction(
	transaction OAuthFirstLoginTransaction,
) error {
	provider, err := normalizeOAuthPostgresProvider(transaction.Provider)
	if err != nil || provider != transaction.Provider ||
		transaction.Purpose != OAuthPurposeFirstLogin ||
		!validOAuthFirstLoginHandle(transaction.StateHash, 128) ||
		!validOAuthFirstLoginHandle(transaction.CodeVerifier, 256) ||
		!validOAuthFirstLoginHandle(transaction.Nonce, 256) ||
		!validOAuthFirstLoginHandle(transaction.IntentID, 256) ||
		!validPostgresIdentityVerificationUUID(transaction.OrganizationID) ||
		!validPostgresIdentityVerificationUUID(transaction.ProjectID) ||
		transaction.CreatedAt.IsZero() ||
		!transaction.ExpiresAt.After(transaction.CreatedAt) ||
		transaction.ExpiresAt.After(transaction.CreatedAt.Add(30*time.Minute)) {
		return errors.New("OAuth first-login transaction is invalid")
	}
	return nil
}

func oauthFirstLoginTransactionBinding(
	transaction OAuthFirstLoginTransaction,
) OAuthSecretBinding {
	handle := "oauth_first_login_transaction:" + transaction.IntentID
	return OAuthSecretBinding{
		Provider: transaction.Provider, TenantID: transaction.OrganizationID,
		ProjectID: transaction.ProjectID, SessionID: handle, UserID: handle,
		AccountID: handle,
	}
}

func validatePostgresOAuthFirstLoginTokenBinding(binding OAuthSecretBinding) error {
	if validatePostgresOAuthBinding(binding) != nil ||
		!validPostgresIdentityVerificationUUID(binding.TenantID) ||
		!validPostgresIdentityVerificationUUID(binding.ProjectID) ||
		binding.SessionID != binding.UserID || binding.SessionID != binding.AccountID ||
		!strings.HasPrefix(binding.SessionID, "oauth_first_login:ofli_") ||
		!validOAuthFirstLoginHandle(binding.SessionID, 512) {
		return errors.New("OAuth first-login token binding is invalid")
	}
	return nil
}

func decodeStrictOAuthFirstLoginVaultEnvelope(
	payload []byte,
	target *oauthFirstLoginVaultEnvelope,
) error {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("OAuth first-login transaction envelope has trailing data")
	}
	return nil
}

func mapPostgresOAuthFirstLoginTransactionError(provider string, err error) error {
	mapped := mapPostgresOAuthTransactionErrorNeutral(provider, err)
	if errors.Is(mapped, ErrOAuthTransactionNotFound) ||
		errors.Is(mapped, ErrOAuthTransactionExpired) {
		return mapped
	}
	return errors.New("consume OAuth first-login runtime transaction failed")
}

var (
	_ OAuthFirstLoginTransactionStore = (*PostgresOAuthFirstLoginStore)(nil)
	_ OAuthSecretStore                = (*PostgresOAuthFirstLoginStore)(nil)
)
