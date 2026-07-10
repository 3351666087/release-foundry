package ashrclone

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/lib/pq"
)

var oauthPostgresProviderPattern = regexp.MustCompile(`^[a-z][a-z0-9_-]{1,31}$`)

// OAuthOpaqueVault keeps provider credentials and transaction payloads outside
// PostgreSQL. The database stores only references and digests.
type OAuthOpaqueVault interface {
	Put(context.Context, string, OAuthSecretBinding, []byte) (string, error)
	Get(context.Context, string) ([]byte, error)
	Binding(context.Context, string) (OAuthSecretBinding, error)
	Delete(context.Context, string) error
}

// PostgresOAuthStore implements the provider-neutral OAuth persistence
// contracts on top of migration 007.
type PostgresOAuthStore struct {
	db    *sql.DB
	vault OAuthOpaqueVault
}

func NewPostgresOAuthStore(db *sql.DB, vault OAuthOpaqueVault) (*PostgresOAuthStore, error) {
	if db == nil {
		return nil, fmt.Errorf("OAuth postgres db is required")
	}
	if vault == nil {
		return nil, fmt.Errorf("OAuth opaque vault is required")
	}
	return &PostgresOAuthStore{db: db, vault: vault}, nil
}

func (store *PostgresOAuthStore) CreateOAuthTransaction(ctx context.Context, transaction OAuthTransaction) error {
	if err := validatePostgresOAuthTransaction(transaction); err != nil {
		return err
	}
	binding := oauthTransactionBinding(transaction)
	payload, err := json.Marshal(transaction)
	if err != nil {
		return fmt.Errorf("encode %s OAuth transaction: %w", transaction.Provider, err)
	}
	ref, err := store.vault.Put(ctx, transaction.Provider+".oauth.transaction", binding, payload)
	if err != nil {
		return fmt.Errorf("vault %s OAuth transaction: %w", transaction.Provider, err)
	}
	if !isOAuthOpaqueReference(ref) {
		_ = store.vault.Delete(ctx, ref)
		return fmt.Errorf("%s OAuth vault returned an invalid opaque reference", transaction.Provider)
	}

	tx, err := store.db.BeginTx(ctx, nil)
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		return fmt.Errorf("begin %s OAuth transaction insert: %w", transaction.Provider, err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(transaction.TenantID, transaction.ProjectID)
	if err := setPostgresOAuthScopeNeutral(ctx, tx, organizationID, projectID); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return err
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO oauth_runtime_transactions (
  organization_id, project_id, provider, state_digest, binding_digest,
  transaction_ref, created_at, expires_at
) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8)
`, organizationID, projectID, transaction.Provider, postgresOAuthDigest(transaction.StateHash),
		postgresOAuthBindingDigestNeutral(binding), ref, transaction.CreatedAt.UTC(), transaction.ExpiresAt.UTC())
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		if postgresOAuthUniqueViolation(err) {
			return fmt.Errorf("OAuth state collision")
		}
		return fmt.Errorf("insert %s OAuth runtime transaction: %w", transaction.Provider, err)
	}
	if err := tx.Commit(); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return fmt.Errorf("commit %s OAuth runtime transaction: %w", transaction.Provider, err)
	}
	return nil
}

func (store *PostgresOAuthStore) ConsumeOAuthTransaction(
	ctx context.Context,
	provider string,
	stateHash string,
	now time.Time,
) (OAuthTransaction, error) {
	provider, err := normalizeOAuthPostgresProvider(provider)
	if err != nil {
		return OAuthTransaction{}, err
	}
	if strings.TrimSpace(stateHash) == "" {
		return OAuthTransaction{}, fmt.Errorf("%s OAuth state hash is required", provider)
	}

	var ref string
	var expiresAt time.Time
	var status string
	err = store.db.QueryRowContext(ctx, `
SELECT transaction_ref, expires_at, status
  FROM a1_consume_oauth_runtime_transaction($1, $2, $3)
`, provider, postgresOAuthDigest(stateHash), now.UTC()).Scan(&ref, &expiresAt, &status)
	if err != nil {
		return OAuthTransaction{}, mapPostgresOAuthTransactionErrorNeutral(provider, err)
	}
	if status == "expired" || !now.Before(expiresAt) {
		return OAuthTransaction{}, ErrOAuthTransactionExpired
	}
	payload, err := store.vault.Get(ctx, ref)
	if err != nil {
		return OAuthTransaction{}, fmt.Errorf("load %s OAuth transaction from vault: %w", provider, err)
	}
	var transaction OAuthTransaction
	if err := json.Unmarshal(payload, &transaction); err != nil {
		return OAuthTransaction{}, fmt.Errorf("decode %s OAuth transaction from vault: %w", provider, err)
	}
	if transaction.Provider != provider || transaction.StateHash != stateHash {
		return OAuthTransaction{}, fmt.Errorf("%s OAuth transaction vault binding mismatch", provider)
	}
	if err := store.vault.Delete(ctx, ref); err != nil {
		return OAuthTransaction{}, fmt.Errorf("delete consumed %s OAuth transaction from vault: %w", provider, err)
	}
	return transaction, nil
}

func (store *PostgresOAuthStore) PutOAuthToken(
	ctx context.Context,
	binding OAuthSecretBinding,
	token string,
) (string, error) {
	if err := validatePostgresOAuthBinding(binding); err != nil {
		return "", err
	}
	if strings.TrimSpace(token) == "" {
		return "", fmt.Errorf("%s OAuth token is required", binding.Provider)
	}
	ref, err := store.vault.Put(ctx, binding.Provider+".oauth.access_token", binding, []byte(token))
	if err != nil {
		return "", fmt.Errorf("vault %s OAuth token: %w", binding.Provider, err)
	}
	if !isOAuthOpaqueReference(ref) {
		_ = store.vault.Delete(ctx, ref)
		return "", fmt.Errorf("%s OAuth vault returned an invalid opaque reference", binding.Provider)
	}

	tx, err := store.db.BeginTx(ctx, nil)
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		return "", fmt.Errorf("begin %s OAuth token insert: %w", binding.Provider, err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(binding.TenantID, binding.ProjectID)
	if err := setPostgresOAuthScopeNeutral(ctx, tx, organizationID, projectID); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return "", err
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO oauth_token_opaque_refs (
  organization_id, project_id, provider, binding_digest,
  opaque_ref, opaque_ref_digest
) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)
`, organizationID, projectID, binding.Provider, postgresOAuthBindingDigestNeutral(binding),
		ref, postgresOAuthDigest(ref))
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		return "", fmt.Errorf("insert %s OAuth opaque token reference: %w", binding.Provider, err)
	}
	if err := tx.Commit(); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return "", fmt.Errorf("commit %s OAuth opaque token reference: %w", binding.Provider, err)
	}
	return ref, nil
}

func (store *PostgresOAuthStore) GetOAuthToken(ctx context.Context, ref string) (string, error) {
	if !isOAuthOpaqueReference(ref) {
		return "", fmt.Errorf("invalid OAuth opaque token reference")
	}
	payload, err := store.vault.Get(ctx, ref)
	if err != nil {
		return "", fmt.Errorf("load OAuth token from vault: %w", err)
	}
	return string(payload), nil
}

func (store *PostgresOAuthStore) DeleteOAuthToken(ctx context.Context, ref string) error {
	if !isOAuthOpaqueReference(ref) {
		return fmt.Errorf("invalid OAuth opaque token reference")
	}

	// Commit the durable revocation first. If vault deletion fails, callers can
	// retry without leaving an active database reference to a missing secret.
	binding, err := store.vault.Binding(ctx, ref)
	if err != nil {
		return fmt.Errorf("resolve OAuth token binding from vault: %w", err)
	}
	if err := validatePostgresOAuthBinding(binding); err != nil {
		return fmt.Errorf("resolve OAuth token binding from vault: %w", err)
	}
	tx, err := store.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin %s OAuth token revocation: %w", binding.Provider, err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(binding.TenantID, binding.ProjectID)
	if err := setPostgresOAuthScopeNeutral(ctx, tx, organizationID, projectID); err != nil {
		return err
	}
	_, err = tx.ExecContext(ctx, `
SELECT id FROM a1_revoke_oauth_token_ref($1, $2)
`, postgresOAuthDigest(ref), time.Now().UTC())
	if err != nil {
		return fmt.Errorf("revoke OAuth opaque token reference: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit %s OAuth token revocation: %w", binding.Provider, err)
	}
	if err := store.vault.Delete(ctx, ref); err != nil {
		return fmt.Errorf("delete OAuth token from vault: %w", err)
	}
	return nil
}

func (store *PostgresOAuthStore) UpsertOAuthConnection(
	ctx context.Context,
	connection OAuthConnection,
) (OAuthConnection, error) {
	binding := oauthConnectionBinding(connection)
	if err := validatePostgresOAuthBinding(binding); err != nil {
		return OAuthConnection{}, err
	}
	if !isOAuthOpaqueReference(connection.TokenRef) {
		return OAuthConnection{}, fmt.Errorf("%s OAuth connection requires an opaque token reference", binding.Provider)
	}
	if !isSHA256Hex(connection.ProviderSubjectHash) {
		return OAuthConnection{}, fmt.Errorf("%s OAuth provider subject digest must be sha256 hex", binding.Provider)
	}

	tx, err := store.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return OAuthConnection{}, fmt.Errorf("begin %s OAuth connection upsert: %w", binding.Provider, err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(binding.TenantID, binding.ProjectID)
	if err := setPostgresOAuthScopeNeutral(ctx, tx, organizationID, projectID); err != nil {
		return OAuthConnection{}, err
	}

	var tokenRefID string
	err = tx.QueryRowContext(ctx, `
SELECT id
  FROM oauth_token_opaque_refs
 WHERE organization_id = $1::uuid AND project_id = $2::uuid
   AND provider = $3 AND opaque_ref_digest = $4 AND status = 'active'
 FOR UPDATE
`, organizationID, projectID, binding.Provider, postgresOAuthDigest(connection.TokenRef)).Scan(&tokenRefID)
	if err != nil {
		return OAuthConnection{}, fmt.Errorf("resolve %s OAuth token reference: %w", binding.Provider, err)
	}

	var previousConnectionID sql.NullString
	var previousTokenRefID sql.NullString
	err = tx.QueryRowContext(ctx, `
SELECT id, token_ref_id
  FROM oauth_account_connections
 WHERE organization_id = $1::uuid AND project_id = $2::uuid
   AND provider = $3 AND account_id = $4
 FOR UPDATE
`, organizationID, projectID, binding.Provider, binding.AccountID).
		Scan(&previousConnectionID, &previousTokenRefID)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return OAuthConnection{}, fmt.Errorf("lock %s OAuth connection: %w", binding.Provider, err)
	}

	emailDigest := sql.NullString{}
	if connection.EmailPresent && strings.TrimSpace(connection.Email) != "" {
		emailDigest = sql.NullString{
			String: postgresOAuthDigest(strings.ToLower(strings.TrimSpace(connection.Email))),
			Valid:  true,
		}
	}
	connectedAt := connection.ConnectedAt.UTC()
	if connectedAt.IsZero() {
		connectedAt = time.Now().UTC()
	}
	displayName := strings.TrimSpace(connection.DisplayName)
	if displayName == "" {
		displayName = binding.Provider
	}
	var row postgresOAuthConnectionRow
	err = tx.QueryRowContext(ctx, `
INSERT INTO oauth_account_connections (
  organization_id, project_id, provider, account_id, session_id, user_id,
  binding_digest, provider_subject_digest, provider_login, email_digest,
  email_present, token_ref_id, status, connected_at, updated_at, disconnected_at
) VALUES (
  $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11,
  $12::uuid, 'active', $13, $13, NULL
)
ON CONFLICT (organization_id, project_id, provider, account_id)
DO UPDATE SET
  session_id = EXCLUDED.session_id,
  user_id = EXCLUDED.user_id,
  binding_digest = EXCLUDED.binding_digest,
  provider_subject_digest = EXCLUDED.provider_subject_digest,
  provider_login = EXCLUDED.provider_login,
  email_digest = EXCLUDED.email_digest,
  email_present = EXCLUDED.email_present,
  token_ref_id = EXCLUDED.token_ref_id,
  status = 'active',
  connected_at = EXCLUDED.connected_at,
  updated_at = EXCLUDED.updated_at,
  disconnected_at = NULL
RETURNING id, account_id, session_id, user_id, provider_subject_digest,
          provider_login, email_present, token_ref_id, connected_at, disconnected_at
`, organizationID, projectID, binding.Provider, binding.AccountID, binding.SessionID,
		binding.UserID, postgresOAuthBindingDigestNeutral(binding), connection.ProviderSubjectHash,
		displayName, emailDigest, connection.EmailPresent, tokenRefID, connectedAt).
		Scan(row.destinations()...)
	if err != nil {
		return OAuthConnection{}, fmt.Errorf("upsert %s OAuth connection: %w", binding.Provider, err)
	}
	if previousTokenRefID.Valid && previousTokenRefID.String != tokenRefID {
		if err := supersedePostgresOAuthTokenNeutral(
			ctx, tx, organizationID, projectID, binding.Provider,
			previousConnectionID.String, previousTokenRefID.String, connectedAt,
		); err != nil {
			return OAuthConnection{}, err
		}
	}
	if err := tx.Commit(); err != nil {
		return OAuthConnection{}, fmt.Errorf("commit %s OAuth connection upsert: %w", binding.Provider, err)
	}
	return row.connection(connection, connection.TokenRef), nil
}

func (store *PostgresOAuthStore) GetOAuthConnection(
	ctx context.Context,
	binding OAuthSecretBinding,
) (OAuthConnection, error) {
	if err := validatePostgresOAuthBinding(binding); err != nil {
		return OAuthConnection{}, err
	}
	tx, err := store.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return OAuthConnection{}, fmt.Errorf("begin %s OAuth connection read: %w", binding.Provider, err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(binding.TenantID, binding.ProjectID)
	if err := setPostgresOAuthScopeNeutral(ctx, tx, organizationID, projectID); err != nil {
		return OAuthConnection{}, err
	}
	var row postgresOAuthConnectionRow
	var tokenRef string
	err = tx.QueryRowContext(ctx, `
SELECT c.id, c.account_id, c.session_id, c.user_id, c.provider_subject_digest,
       c.provider_login, c.email_present, c.token_ref_id, c.connected_at,
       c.disconnected_at, t.opaque_ref
  FROM oauth_account_connections c
  JOIN oauth_token_opaque_refs t
    ON t.organization_id = c.organization_id
   AND t.project_id = c.project_id
   AND t.id = c.token_ref_id
 WHERE c.organization_id = $1::uuid AND c.project_id = $2::uuid
   AND c.provider = $3 AND c.account_id = $4
   AND c.binding_digest = $5 AND c.status = 'active'
`, organizationID, projectID, binding.Provider, binding.AccountID,
		postgresOAuthBindingDigestNeutral(binding)).Scan(append(row.destinations(), &tokenRef)...)
	if errors.Is(err, sql.ErrNoRows) {
		return OAuthConnection{}, ErrOAuthConnectionNotFound
	}
	if err != nil {
		return OAuthConnection{}, fmt.Errorf("read %s OAuth connection: %w", binding.Provider, err)
	}
	if err := tx.Commit(); err != nil {
		return OAuthConnection{}, fmt.Errorf("commit %s OAuth connection read: %w", binding.Provider, err)
	}
	base := OAuthConnection{
		SchemaVersion: OAuthConnectionSchemaVersion, Provider: binding.Provider,
		TenantID: binding.TenantID, ProjectID: binding.ProjectID,
	}
	return row.connection(base, tokenRef), nil
}

func (store *PostgresOAuthStore) DisconnectOAuthConnection(
	ctx context.Context,
	binding OAuthSecretBinding,
	at time.Time,
) (OAuthConnection, error) {
	if err := validatePostgresOAuthBinding(binding); err != nil {
		return OAuthConnection{}, err
	}
	tx, err := store.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return OAuthConnection{}, fmt.Errorf("begin %s OAuth disconnect: %w", binding.Provider, err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(binding.TenantID, binding.ProjectID)
	if err := setPostgresOAuthScopeNeutral(ctx, tx, organizationID, projectID); err != nil {
		return OAuthConnection{}, err
	}

	var row postgresOAuthConnectionRow
	var tokenRef string
	var tokenStatus string
	err = tx.QueryRowContext(ctx, `
SELECT c.id, c.account_id, c.session_id, c.user_id, c.provider_subject_digest,
       c.provider_login, c.email_present, c.token_ref_id, c.connected_at,
       c.disconnected_at, t.opaque_ref, t.status
  FROM oauth_account_connections c
  JOIN oauth_token_opaque_refs t
    ON t.organization_id = c.organization_id
   AND t.project_id = c.project_id
   AND t.id = c.token_ref_id
 WHERE c.organization_id = $1::uuid AND c.project_id = $2::uuid
   AND c.provider = $3 AND c.account_id = $4
   AND c.binding_digest = $5 AND c.status = 'active'
 FOR UPDATE OF c, t
`, organizationID, projectID, binding.Provider, binding.AccountID,
		postgresOAuthBindingDigestNeutral(binding)).
		Scan(append(row.destinations(), &tokenRef, &tokenStatus)...)
	if errors.Is(err, sql.ErrNoRows) {
		return OAuthConnection{}, ErrOAuthConnectionNotFound
	}
	if err != nil {
		return OAuthConnection{}, fmt.Errorf("lock %s OAuth connection for disconnect: %w", binding.Provider, err)
	}

	at = at.UTC()
	if at.IsZero() {
		at = time.Now().UTC()
	}
	if _, err = tx.ExecContext(ctx, `
UPDATE oauth_account_connections
   SET status = 'disconnected', disconnected_at = $4, updated_at = $4
 WHERE organization_id = $1::uuid AND project_id = $2::uuid AND id = $3::uuid
`, organizationID, projectID, row.id, at); err != nil {
		return OAuthConnection{}, fmt.Errorf("disconnect %s OAuth connection: %w", binding.Provider, err)
	}
	if tokenStatus != "revoked" {
		if _, err = tx.ExecContext(ctx, `
UPDATE oauth_token_opaque_refs
   SET status = 'revocation_pending'
 WHERE organization_id = $1::uuid AND project_id = $2::uuid AND id = $3::uuid
   AND status <> 'revoked';
INSERT INTO oauth_revocation_outbox (
  organization_id, project_id, provider, connection_id, token_ref_id,
  operation_kind, reason_code, available_at, created_at, updated_at
) VALUES (
  $1::uuid, $2::uuid, $4, $5::uuid, $3::uuid,
  'provider_revoke_and_cleanup', 'disconnect', $6, $6, $6
)
ON CONFLICT (token_ref_id) DO NOTHING
`, organizationID, projectID, row.tokenRefID, binding.Provider, row.id, at); err != nil {
			return OAuthConnection{}, fmt.Errorf("enqueue %s OAuth revocation: %w", binding.Provider, err)
		}
	}
	if err := tx.Commit(); err != nil {
		return OAuthConnection{}, fmt.Errorf("commit %s OAuth disconnect: %w", binding.Provider, err)
	}
	disconnected := at
	result := row.connection(OAuthConnection{
		SchemaVersion: OAuthConnectionSchemaVersion, Provider: binding.Provider,
		TenantID: binding.TenantID, ProjectID: binding.ProjectID,
	}, "")
	result.DisconnectedAt = &disconnected
	return result, nil
}

type postgresOAuthConnectionRow struct {
	id                    string
	accountID             string
	sessionID             string
	userID                string
	providerSubjectDigest string
	displayName           string
	emailPresent          bool
	tokenRefID            string
	connectedAt           time.Time
	disconnectedAt        sql.NullTime
}

func (row *postgresOAuthConnectionRow) destinations() []any {
	return []any{
		&row.id, &row.accountID, &row.sessionID, &row.userID,
		&row.providerSubjectDigest, &row.displayName, &row.emailPresent,
		&row.tokenRefID, &row.connectedAt, &row.disconnectedAt,
	}
}

func (row postgresOAuthConnectionRow) connection(base OAuthConnection, tokenRef string) OAuthConnection {
	base.SchemaVersion = OAuthConnectionSchemaVersion
	base.AccountID = row.accountID
	base.SessionID = row.sessionID
	base.UserID = row.userID
	base.CredentialID = "cred_" + strings.ReplaceAll(row.id, "-", "")
	base.ProviderSubjectHash = row.providerSubjectDigest
	base.ProviderSubjectPresent = row.providerSubjectDigest != ""
	base.DisplayName = row.displayName
	base.EmailPresent = row.emailPresent
	base.Email = ""
	base.TokenRef = tokenRef
	base.ConnectedAt = row.connectedAt
	if row.disconnectedAt.Valid {
		value := row.disconnectedAt.Time
		base.DisconnectedAt = &value
	}
	return base
}

func supersedePostgresOAuthTokenNeutral(
	ctx context.Context,
	tx *sql.Tx,
	organizationID string,
	projectID string,
	provider string,
	connectionID string,
	tokenRefID string,
	at time.Time,
) error {
	_, err := tx.ExecContext(ctx, `
UPDATE oauth_token_opaque_refs
   SET status = 'superseded', superseded_at = $5
 WHERE organization_id = $1::uuid AND project_id = $2::uuid AND id = $3::uuid
   AND status = 'active';
INSERT INTO oauth_revocation_outbox (
  organization_id, project_id, provider, connection_id, token_ref_id,
  operation_kind, reason_code, available_at, created_at, updated_at
) VALUES (
  $1::uuid, $2::uuid, $4, $6::uuid, $3::uuid,
  'provider_revoke_and_cleanup', 'superseded', $5, $5, $5
)
ON CONFLICT (token_ref_id) DO NOTHING
`, organizationID, projectID, tokenRefID, provider, at, connectionID)
	if err != nil {
		return fmt.Errorf("supersede previous %s OAuth token: %w", provider, err)
	}
	return nil
}

func setPostgresOAuthScopeNeutral(
	ctx context.Context,
	tx *sql.Tx,
	organizationID string,
	projectID string,
) error {
	if _, err := tx.ExecContext(ctx, `
SELECT set_config('app.a1_organization_id', $1, true),
       set_config('app.a1_project_id', $2, true)
`, organizationID, projectID); err != nil {
		return fmt.Errorf("set OAuth tenant context: %w", err)
	}
	return nil
}

func normalizeOAuthPostgresProvider(provider string) (string, error) {
	normalized := strings.ToLower(strings.TrimSpace(provider))
	if provider != normalized || !oauthPostgresProviderPattern.MatchString(normalized) {
		return "", fmt.Errorf("OAuth provider must match %s", oauthPostgresProviderPattern.String())
	}
	return normalized, nil
}

func validatePostgresOAuthBinding(binding OAuthSecretBinding) error {
	provider, err := normalizeOAuthPostgresProvider(binding.Provider)
	if err != nil {
		return err
	}
	binding.Provider = provider
	for name, value := range map[string]string{
		"tenant_id": binding.TenantID, "project_id": binding.ProjectID,
		"session_id": binding.SessionID, "user_id": binding.UserID, "account_id": binding.AccountID,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s OAuth %s is required", binding.Provider, name)
		}
	}
	return nil
}

func validatePostgresOAuthTransaction(transaction OAuthTransaction) error {
	provider, err := normalizeOAuthPostgresProvider(transaction.Provider)
	if err != nil {
		return err
	}
	transaction.Provider = provider
	if strings.TrimSpace(transaction.StateHash) == "" || strings.TrimSpace(transaction.CodeVerifier) == "" {
		return fmt.Errorf("%s OAuth transaction state hash and verifier are required", provider)
	}
	if err := validatePostgresOAuthBinding(oauthTransactionBinding(transaction)); err != nil {
		return err
	}
	if transaction.CreatedAt.IsZero() || !transaction.ExpiresAt.After(transaction.CreatedAt) {
		return fmt.Errorf("%s OAuth transaction TTL is invalid", provider)
	}
	return nil
}

func oauthTransactionBinding(transaction OAuthTransaction) OAuthSecretBinding {
	return OAuthSecretBinding{
		Provider: transaction.Provider, TenantID: transaction.TenantID, ProjectID: transaction.ProjectID,
		SessionID: transaction.SessionID, UserID: transaction.UserID, AccountID: transaction.AccountID,
	}
}

func oauthConnectionBinding(connection OAuthConnection) OAuthSecretBinding {
	return OAuthSecretBinding{
		Provider: connection.Provider, TenantID: connection.TenantID, ProjectID: connection.ProjectID,
		SessionID: connection.SessionID, UserID: connection.UserID, AccountID: connection.AccountID,
	}
}

func postgresOAuthBindingDigestNeutral(binding OAuthSecretBinding) string {
	return postgresOAuthDigest(oauthBindingKey(binding))
}

func isSHA256Hex(value string) bool {
	if len(value) != 64 {
		return false
	}
	for _, char := range value {
		if (char < '0' || char > '9') && (char < 'a' || char > 'f') {
			return false
		}
	}
	return true
}

func mapPostgresOAuthTransactionErrorNeutral(provider string, err error) error {
	if postgresOAuthNoData(err) || errors.Is(err, sql.ErrNoRows) {
		return ErrOAuthTransactionNotFound
	}
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		switch string(pqErr.Code) {
		case "23505":
			return ErrOAuthTransactionNotFound
		case "22023":
			if strings.Contains(strings.ToLower(pqErr.Message), "expired") {
				return ErrOAuthTransactionExpired
			}
		}
	}
	return fmt.Errorf("consume %s OAuth runtime transaction: %w", provider, err)
}

var (
	_ OAuthTransactionStore = (*PostgresOAuthStore)(nil)
	_ OAuthSecretStore      = (*PostgresOAuthStore)(nil)
	_ OAuthConnectionStore  = (*PostgresOAuthStore)(nil)
)
