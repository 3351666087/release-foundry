package ashrclone

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/lib/pq"
)

const githubOAuthPostgresProvider = "github"

type GitHubOAuthOpaqueVault interface {
	Put(context.Context, string, GitHubOAuthSecretBinding, []byte) (string, error)
	Get(context.Context, string) ([]byte, error)
	Delete(context.Context, string) error
}

type PostgresGitHubOAuthStore struct {
	db    *sql.DB
	vault GitHubOAuthOpaqueVault
}

func NewPostgresGitHubOAuthStore(db *sql.DB, vault GitHubOAuthOpaqueVault) (*PostgresGitHubOAuthStore, error) {
	if db == nil {
		return nil, fmt.Errorf("GitHub OAuth postgres db is required")
	}
	if vault == nil {
		return nil, fmt.Errorf("GitHub OAuth opaque vault is required")
	}
	return &PostgresGitHubOAuthStore{db: db, vault: vault}, nil
}

func (store *PostgresGitHubOAuthStore) CreateGitHubOAuthTransaction(ctx context.Context, transaction GitHubOAuthTransaction) error {
	if err := validateGitHubOAuthTransaction(transaction); err != nil {
		return err
	}
	binding := githubOAuthTransactionBinding(transaction)
	payload, err := json.Marshal(transaction)
	if err != nil {
		return fmt.Errorf("encode GitHub OAuth transaction: %w", err)
	}
	ref, err := store.vault.Put(ctx, "github.oauth.transaction", binding, payload)
	if err != nil {
		return fmt.Errorf("vault GitHub OAuth transaction: %w", err)
	}
	if !isOAuthOpaqueReference(ref) {
		_ = store.vault.Delete(ctx, ref)
		return fmt.Errorf("GitHub OAuth vault returned an invalid opaque reference")
	}

	tx, err := store.db.BeginTx(ctx, nil)
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		return fmt.Errorf("begin GitHub OAuth transaction insert: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(transaction.TenantID, transaction.ProjectID)
	if err := setPostgresOAuthScope(ctx, tx, organizationID, projectID); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return err
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO oauth_runtime_transactions (
  organization_id, project_id, provider, state_digest, binding_digest,
  transaction_ref, created_at, expires_at
) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8)
`, organizationID, projectID, githubOAuthPostgresProvider,
		postgresOAuthDigest(transaction.StateHash), postgresOAuthBindingDigest(binding),
		ref, transaction.CreatedAt.UTC(), transaction.ExpiresAt.UTC())
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		if postgresOAuthUniqueViolation(err) {
			return fmt.Errorf("OAuth state collision")
		}
		return fmt.Errorf("insert GitHub OAuth runtime transaction: %w", err)
	}
	if err := tx.Commit(); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return fmt.Errorf("commit GitHub OAuth runtime transaction: %w", err)
	}
	return nil
}

func (store *PostgresGitHubOAuthStore) ConsumeGitHubOAuthTransaction(ctx context.Context, stateHash string, now time.Time) (GitHubOAuthTransaction, error) {
	var ref string
	var expiresAt time.Time
	var status string
	err := store.db.QueryRowContext(ctx, `
SELECT transaction_ref, expires_at, status
  FROM a1_consume_oauth_runtime_transaction($1, $2, $3)
`, githubOAuthPostgresProvider, postgresOAuthDigest(stateHash), now.UTC()).Scan(&ref, &expiresAt, &status)
	if err != nil {
		return GitHubOAuthTransaction{}, mapPostgresOAuthTransactionError(err)
	}
	if status == "expired" || !now.Before(expiresAt) {
		return GitHubOAuthTransaction{}, ErrGitHubOAuthTransactionExpired
	}
	payload, err := store.vault.Get(ctx, ref)
	if err != nil {
		return GitHubOAuthTransaction{}, fmt.Errorf("load GitHub OAuth transaction from vault: %w", err)
	}
	var transaction GitHubOAuthTransaction
	if err := json.Unmarshal(payload, &transaction); err != nil {
		return GitHubOAuthTransaction{}, fmt.Errorf("decode GitHub OAuth transaction from vault: %w", err)
	}
	if transaction.StateHash != stateHash {
		return GitHubOAuthTransaction{}, fmt.Errorf("GitHub OAuth transaction vault binding mismatch")
	}
	if err := store.vault.Delete(ctx, ref); err != nil {
		return GitHubOAuthTransaction{}, fmt.Errorf("delete consumed GitHub OAuth transaction from vault: %w", err)
	}
	return transaction, nil
}

func (store *PostgresGitHubOAuthStore) PutGitHubOAuthToken(ctx context.Context, binding GitHubOAuthSecretBinding, token string) (string, error) {
	if err := validatePostgresGitHubOAuthBinding(binding); err != nil {
		return "", err
	}
	if strings.TrimSpace(token) == "" {
		return "", fmt.Errorf("GitHub OAuth token is required")
	}
	ref, err := store.vault.Put(ctx, "github.oauth.access_token", binding, []byte(token))
	if err != nil {
		return "", fmt.Errorf("vault GitHub OAuth token: %w", err)
	}
	if !isOAuthOpaqueReference(ref) {
		_ = store.vault.Delete(ctx, ref)
		return "", fmt.Errorf("GitHub OAuth vault returned an invalid opaque reference")
	}
	tx, err := store.db.BeginTx(ctx, nil)
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		return "", fmt.Errorf("begin GitHub OAuth token insert: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(binding.TenantID, binding.ProjectID)
	if err := setPostgresOAuthScope(ctx, tx, organizationID, projectID); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return "", err
	}
	_, err = tx.ExecContext(ctx, `
INSERT INTO oauth_token_opaque_refs (
  organization_id, project_id, provider, binding_digest,
  opaque_ref, opaque_ref_digest
) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)
`, organizationID, projectID, githubOAuthPostgresProvider,
		postgresOAuthBindingDigest(binding), ref, postgresOAuthDigest(ref))
	if err != nil {
		_ = store.vault.Delete(ctx, ref)
		return "", fmt.Errorf("insert GitHub OAuth opaque token reference: %w", err)
	}
	if err := tx.Commit(); err != nil {
		_ = store.vault.Delete(ctx, ref)
		return "", fmt.Errorf("commit GitHub OAuth opaque token reference: %w", err)
	}
	return ref, nil
}

func (store *PostgresGitHubOAuthStore) GetGitHubOAuthToken(ctx context.Context, ref string) (string, error) {
	if !isOAuthOpaqueReference(ref) {
		return "", fmt.Errorf("invalid GitHub OAuth opaque token reference")
	}
	payload, err := store.vault.Get(ctx, ref)
	if err != nil {
		return "", fmt.Errorf("load GitHub OAuth token from vault: %w", err)
	}
	return string(payload), nil
}

func (store *PostgresGitHubOAuthStore) DeleteGitHubOAuthToken(ctx context.Context, ref string) error {
	if !isOAuthOpaqueReference(ref) {
		return fmt.Errorf("invalid GitHub OAuth opaque token reference")
	}
	if err := store.vault.Delete(ctx, ref); err != nil {
		return fmt.Errorf("delete GitHub OAuth token from vault: %w", err)
	}
	_, err := store.db.ExecContext(ctx, `
SELECT id FROM a1_revoke_oauth_token_ref($1, $2)
`, postgresOAuthDigest(ref), time.Now().UTC())
	if err != nil && !postgresOAuthNoData(err) {
		return fmt.Errorf("revoke GitHub OAuth opaque token reference: %w", err)
	}
	return nil
}

func (store *PostgresGitHubOAuthStore) UpsertGitHubOAuthConnection(ctx context.Context, connection GitHubOAuthConnection) (GitHubOAuthConnection, error) {
	binding := GitHubOAuthSecretBinding{
		TenantID: connection.TenantID, ProjectID: connection.ProjectID,
		SessionID: connection.SessionID, UserID: connection.UserID, AccountID: connection.AccountID,
	}
	if err := validatePostgresGitHubOAuthBinding(binding); err != nil {
		return GitHubOAuthConnection{}, err
	}
	if !isOAuthOpaqueReference(connection.TokenRef) {
		return GitHubOAuthConnection{}, fmt.Errorf("GitHub OAuth connection requires an opaque token reference")
	}
	tx, err := store.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("begin GitHub OAuth connection upsert: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(connection.TenantID, connection.ProjectID)
	if err := setPostgresOAuthScope(ctx, tx, organizationID, projectID); err != nil {
		return GitHubOAuthConnection{}, err
	}

	var tokenRefID string
	err = tx.QueryRowContext(ctx, `
SELECT id
  FROM oauth_token_opaque_refs
 WHERE organization_id = $1::uuid AND project_id = $2::uuid
   AND provider = $3 AND opaque_ref_digest = $4 AND status = 'active'
 FOR UPDATE
`, organizationID, projectID, githubOAuthPostgresProvider,
		postgresOAuthDigest(connection.TokenRef)).Scan(&tokenRefID)
	if err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("resolve GitHub OAuth token reference: %w", err)
	}

	var previousTokenRefID sql.NullString
	var previousConnectionID sql.NullString
	err = tx.QueryRowContext(ctx, `
SELECT id, token_ref_id
  FROM oauth_account_connections
 WHERE organization_id = $1::uuid AND project_id = $2::uuid
   AND provider = $3 AND account_id = $4
 FOR UPDATE
`, organizationID, projectID, githubOAuthPostgresProvider, connection.AccountID).
		Scan(&previousConnectionID, &previousTokenRefID)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return GitHubOAuthConnection{}, fmt.Errorf("lock GitHub OAuth connection: %w", err)
	}

	emailDigest := sql.NullString{}
	if connection.EmailPresent && strings.TrimSpace(connection.Email) != "" {
		emailDigest = sql.NullString{String: postgresOAuthDigest(strings.ToLower(strings.TrimSpace(connection.Email))), Valid: true}
	}
	providerSubjectDigest := strings.ToLower(strings.TrimSpace(connection.ProviderSubjectHash))
	if len(providerSubjectDigest) != 64 {
		providerSubjectDigest = postgresOAuthDigest(fmt.Sprintf("github:%d", connection.GitHubUserID))
	}
	connectedAt := connection.ConnectedAt.UTC()
	if connectedAt.IsZero() {
		connectedAt = time.Now().UTC()
	}
	var row postgresGitHubOAuthConnectionRow
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
`, organizationID, projectID, githubOAuthPostgresProvider, connection.AccountID,
		connection.SessionID, connection.UserID, postgresOAuthBindingDigest(binding),
		providerSubjectDigest, connection.GitHubLogin, emailDigest, connection.EmailPresent,
		tokenRefID, connectedAt).Scan(row.destinations()...)
	if err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("upsert GitHub OAuth connection: %w", err)
	}
	if previousTokenRefID.Valid && previousTokenRefID.String != tokenRefID {
		if err := supersedePostgresOAuthToken(ctx, tx, organizationID, projectID, previousConnectionID.String, previousTokenRefID.String, connectedAt); err != nil {
			return GitHubOAuthConnection{}, err
		}
	}
	if err := tx.Commit(); err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("commit GitHub OAuth connection upsert: %w", err)
	}
	return row.connection(connection, connection.TokenRef), nil
}

func (store *PostgresGitHubOAuthStore) GetGitHubOAuthConnection(ctx context.Context, binding GitHubOAuthSecretBinding) (GitHubOAuthConnection, error) {
	if err := validatePostgresGitHubOAuthBinding(binding); err != nil {
		return GitHubOAuthConnection{}, err
	}
	tx, err := store.db.BeginTx(ctx, &sql.TxOptions{ReadOnly: true})
	if err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("begin GitHub OAuth connection read: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(binding.TenantID, binding.ProjectID)
	if err := setPostgresOAuthScope(ctx, tx, organizationID, projectID); err != nil {
		return GitHubOAuthConnection{}, err
	}
	var row postgresGitHubOAuthConnectionRow
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
`, organizationID, projectID, githubOAuthPostgresProvider, binding.AccountID,
		postgresOAuthBindingDigest(binding)).Scan(append(row.destinations(), &tokenRef)...)
	if errors.Is(err, sql.ErrNoRows) {
		return GitHubOAuthConnection{}, ErrGitHubOAuthConnectionNotFound
	}
	if err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("read GitHub OAuth connection: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("commit GitHub OAuth connection read: %w", err)
	}
	return row.connection(GitHubOAuthConnection{TenantID: binding.TenantID, ProjectID: binding.ProjectID}, tokenRef), nil
}

func (store *PostgresGitHubOAuthStore) DisconnectGitHubOAuthConnection(ctx context.Context, binding GitHubOAuthSecretBinding, at time.Time) (GitHubOAuthConnection, error) {
	if err := validatePostgresGitHubOAuthBinding(binding); err != nil {
		return GitHubOAuthConnection{}, err
	}
	tx, err := store.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("begin GitHub OAuth disconnect: %w", err)
	}
	defer rollbackUnlessCommitted(tx)
	organizationID, projectID := postgresOAuthScope(binding.TenantID, binding.ProjectID)
	if err := setPostgresOAuthScope(ctx, tx, organizationID, projectID); err != nil {
		return GitHubOAuthConnection{}, err
	}
	var row postgresGitHubOAuthConnectionRow
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
 FOR UPDATE OF c, t
`, organizationID, projectID, githubOAuthPostgresProvider, binding.AccountID,
		postgresOAuthBindingDigest(binding)).Scan(append(row.destinations(), &tokenRef)...)
	if errors.Is(err, sql.ErrNoRows) {
		return GitHubOAuthConnection{}, ErrGitHubOAuthConnectionNotFound
	}
	if err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("lock GitHub OAuth connection for disconnect: %w", err)
	}
	at = at.UTC()
	_, err = tx.ExecContext(ctx, `
UPDATE oauth_account_connections
   SET status = 'disconnected', disconnected_at = $4, updated_at = $4
 WHERE organization_id = $1::uuid AND project_id = $2::uuid AND id = $3::uuid;
UPDATE oauth_token_opaque_refs
   SET status = 'revocation_pending'
 WHERE organization_id = $1::uuid AND project_id = $2::uuid AND id = $5::uuid
   AND status <> 'revoked';
INSERT INTO oauth_revocation_outbox (
  organization_id, project_id, provider, connection_id, token_ref_id,
  reason_code, available_at, created_at, updated_at
) VALUES ($1::uuid, $2::uuid, $6, $3::uuid, $5::uuid, 'disconnect', $4, $4, $4)
ON CONFLICT (token_ref_id) DO NOTHING
`, organizationID, projectID, row.id, at, row.tokenRefID, githubOAuthPostgresProvider)
	if err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("disconnect GitHub OAuth connection: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return GitHubOAuthConnection{}, fmt.Errorf("commit GitHub OAuth disconnect: %w", err)
	}
	disconnected := at
	result := row.connection(GitHubOAuthConnection{TenantID: binding.TenantID, ProjectID: binding.ProjectID}, "")
	result.DisconnectedAt = &disconnected
	return result, nil
}

type postgresGitHubOAuthConnectionRow struct {
	id                    string
	accountID             string
	sessionID             string
	userID                string
	providerSubjectDigest string
	providerLogin         string
	emailPresent          bool
	tokenRefID            string
	connectedAt           time.Time
	disconnectedAt        sql.NullTime
}

func (row *postgresGitHubOAuthConnectionRow) destinations() []any {
	return []any{
		&row.id, &row.accountID, &row.sessionID, &row.userID,
		&row.providerSubjectDigest, &row.providerLogin, &row.emailPresent,
		&row.tokenRefID, &row.connectedAt, &row.disconnectedAt,
	}
}

func (row postgresGitHubOAuthConnectionRow) connection(base GitHubOAuthConnection, tokenRef string) GitHubOAuthConnection {
	base.SchemaVersion = GitHubOAuthSchemaVersion
	base.AccountID = row.accountID
	base.SessionID = row.sessionID
	base.UserID = row.userID
	base.CredentialID = "cred_" + strings.ReplaceAll(row.id, "-", "")
	base.ProviderSubjectHash = row.providerSubjectDigest
	base.ProviderSubjectPresent = row.providerSubjectDigest != ""
	base.GitHubLogin = row.providerLogin
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

func supersedePostgresOAuthToken(ctx context.Context, tx *sql.Tx, organizationID, projectID, connectionID, tokenRefID string, at time.Time) error {
	_, err := tx.ExecContext(ctx, `
UPDATE oauth_token_opaque_refs
   SET status = 'superseded', superseded_at = $5
 WHERE organization_id = $1::uuid AND project_id = $2::uuid AND id = $3::uuid
   AND status = 'active';
INSERT INTO oauth_revocation_outbox (
  organization_id, project_id, provider, connection_id, token_ref_id,
  reason_code, available_at, created_at, updated_at
) VALUES ($1::uuid, $2::uuid, $4, $6::uuid, $3::uuid, 'superseded', $5, $5, $5)
ON CONFLICT (token_ref_id) DO NOTHING
`, organizationID, projectID, tokenRefID, githubOAuthPostgresProvider, at, connectionID)
	if err != nil {
		return fmt.Errorf("supersede previous GitHub OAuth token: %w", err)
	}
	return nil
}

func setPostgresOAuthScope(ctx context.Context, tx *sql.Tx, organizationID, projectID string) error {
	if _, err := tx.ExecContext(ctx, `
SELECT set_config('app.a1_organization_id', $1, true),
       set_config('app.a1_project_id', $2, true)
`, organizationID, projectID); err != nil {
		return fmt.Errorf("set GitHub OAuth tenant context: %w", err)
	}
	return nil
}

func postgresOAuthScope(tenantID, projectID string) (string, string) {
	return postgresBillingUUID("org", tenantID), postgresBillingUUID("project", projectID)
}

func postgresOAuthDigest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func postgresOAuthBindingDigest(binding GitHubOAuthSecretBinding) string {
	return postgresOAuthDigest(githubOAuthBindingKey(binding))
}

func githubOAuthTransactionBinding(transaction GitHubOAuthTransaction) GitHubOAuthSecretBinding {
	return GitHubOAuthSecretBinding{
		TenantID: transaction.TenantID, ProjectID: transaction.ProjectID,
		SessionID: transaction.SessionID, UserID: transaction.UserID, AccountID: transaction.AccountID,
	}
}

func validateGitHubOAuthTransaction(transaction GitHubOAuthTransaction) error {
	if strings.TrimSpace(transaction.StateHash) == "" || strings.TrimSpace(transaction.CodeVerifier) == "" {
		return fmt.Errorf("GitHub OAuth transaction state hash and verifier are required")
	}
	if err := validatePostgresGitHubOAuthBinding(githubOAuthTransactionBinding(transaction)); err != nil {
		return err
	}
	if transaction.CreatedAt.IsZero() || !transaction.ExpiresAt.After(transaction.CreatedAt) {
		return fmt.Errorf("GitHub OAuth transaction TTL is invalid")
	}
	return nil
}

func validatePostgresGitHubOAuthBinding(binding GitHubOAuthSecretBinding) error {
	for name, value := range map[string]string{
		"tenant_id": binding.TenantID, "project_id": binding.ProjectID,
		"session_id": binding.SessionID, "user_id": binding.UserID, "account_id": binding.AccountID,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("GitHub OAuth %s is required", name)
		}
	}
	return nil
}

func isOAuthOpaqueReference(ref string) bool {
	if len(ref) < 8 || len(ref) > 1024 || strings.ContainsAny(ref, " \t\r\n") {
		return false
	}
	for _, prefix := range []string{"vault:", "env:", "kms:", "secret:", "provider-ref:", "opaque-ref:"} {
		if strings.HasPrefix(ref, prefix) {
			return true
		}
	}
	return false
}

func mapPostgresOAuthTransactionError(err error) error {
	if postgresOAuthNoData(err) || errors.Is(err, sql.ErrNoRows) {
		return ErrGitHubOAuthTransactionNotFound
	}
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		switch string(pqErr.Code) {
		case "23505":
			return ErrGitHubOAuthTransactionNotFound
		case "22023":
			if strings.Contains(strings.ToLower(pqErr.Message), "expired") {
				return ErrGitHubOAuthTransactionExpired
			}
		}
	}
	return fmt.Errorf("consume GitHub OAuth runtime transaction: %w", err)
}

func postgresOAuthNoData(err error) bool {
	var pqErr *pq.Error
	return errors.As(err, &pqErr) && string(pqErr.Code) == "P0002"
}

func postgresOAuthUniqueViolation(err error) bool {
	var pqErr *pq.Error
	return errors.As(err, &pqErr) && string(pqErr.Code) == "23505"
}
