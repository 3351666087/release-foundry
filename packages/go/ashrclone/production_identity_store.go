package ashrclone

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"fmt"
	"net/http"
	"strings"

	_ "github.com/lib/pq"
)

const (
	IdentityRuntimePostgres = "postgres"
	IdentityRuntimeMemory   = "memory"
)

const productionIdentityReadinessQuery = `
SELECT to_regclass('public.identity_principals') IS NOT NULL
   AND to_regclass('public.identity_credentials') IS NOT NULL
   AND to_regclass('public.identity_sessions') IS NOT NULL
   AND to_regclass('public.oauth_runtime_transactions') IS NOT NULL
   AND to_regclass('public.oauth_account_connections') IS NOT NULL
   AND to_regclass('public.oauth_revocation_outbox') IS NOT NULL
   AND to_regprocedure(
     'public.a1_complete_oauth_identity_callback(uuid,uuid,uuid,text,text,text,text,text,text,text,text,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_disconnect_oauth_identity_credential(uuid,uuid,uuid,uuid,uuid,text,text,text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_authenticate_identity_session_digest(text)'
   ) IS NOT NULL
`

type ProductionIdentityStore struct {
	db         *sql.DB
	sessionKey []byte
}

type ProductionIdentityStoreOptions struct {
	DB         *sql.DB
	SessionKey []byte
}

func NewProductionIdentityStore(options ProductionIdentityStoreOptions) (*ProductionIdentityStore, error) {
	if options.DB == nil {
		return nil, fmt.Errorf("production identity postgres db is required")
	}
	if len(options.SessionKey) < 32 {
		return nil, fmt.Errorf("production identity session HMAC key must contain at least 32 bytes")
	}
	return &ProductionIdentityStore{
		db:         options.DB,
		sessionKey: append([]byte(nil), options.SessionKey...),
	}, nil
}

func OpenProductionIdentityStore(dsn string, sessionKey []byte) (*ProductionIdentityStore, error) {
	dsn = strings.TrimSpace(dsn)
	if dsn == "" {
		return nil, fmt.Errorf("production identity requires ASHR_POSTGRES_DSN or DATABASE_URL")
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("open production identity postgres: %w", err)
	}
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{DB: db, SessionKey: sessionKey})
	if err != nil {
		_ = db.Close()
		return nil, err
	}
	return store, nil
}

func (store *ProductionIdentityStore) Close() error {
	if store == nil || store.db == nil {
		return nil
	}
	for index := range store.sessionKey {
		store.sessionKey[index] = 0
	}
	return store.db.Close()
}

func (store *ProductionIdentityStore) Ready(ctx context.Context) error {
	if store == nil || store.db == nil {
		return fmt.Errorf("production identity store is not configured")
	}
	if err := store.db.PingContext(ctx); err != nil {
		return fmt.Errorf("ping production identity postgres: %w", err)
	}
	var ready bool
	err := store.db.QueryRowContext(ctx, productionIdentityReadinessQuery).Scan(&ready)
	if err != nil {
		return fmt.Errorf("verify production identity schema: %w", err)
	}
	if !ready {
		return fmt.Errorf("production identity PostgreSQL schema is incomplete; migrations 007-011 are required")
	}
	return nil
}

func (store *ProductionIdentityStore) NewOAuthStore(vault OAuthOpaqueVault) (*PostgresOAuthStore, error) {
	if store == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	return NewPostgresOAuthStore(store.db, vault)
}

func (store *ProductionIdentityStore) NewGitHubOAuthStore(vault GitHubOAuthOpaqueVault) (*PostgresGitHubOAuthStore, error) {
	if store == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	return NewPostgresGitHubOAuthStore(store.db, vault)
}

func (store *ProductionIdentityStore) NewOAuthRevocationOutboxStore() (*PostgresOAuthRevocationOutboxStore, error) {
	if store == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	return NewPostgresOAuthRevocationOutboxStore(store.db)
}

type postgresIdentitySession struct {
	AccountID string
	ActorID   string
	SessionID string
	TenantID  string
	ProjectID string
	UserID    string
	Revoked   bool
}

func (store *ProductionIdentityStore) resolveSession(ctx context.Context, request *http.Request) (postgresIdentitySession, error) {
	if store == nil || store.db == nil {
		return postgresIdentitySession{}, fmt.Errorf("production identity session store is unavailable")
	}
	token, err := bearerToken(request)
	if err != nil {
		return postgresIdentitySession{}, err
	}
	digest := store.sessionDigest(token)
	var session postgresIdentitySession
	err = store.db.QueryRowContext(ctx, `
SELECT authenticated.principal_id::text,
       authenticated.principal_id::text,
       authenticated.session_id::text,
       COALESCE(authenticated.organization_id::text, ''),
       COALESCE(authenticated.project_id::text, ''),
       authenticated.principal_id::text
  FROM a1_authenticate_identity_session_digest($1) AS authenticated
`, digest).Scan(
		&session.AccountID,
		&session.ActorID,
		&session.SessionID,
		&session.TenantID,
		&session.ProjectID,
		&session.UserID,
	)
	if err == sql.ErrNoRows {
		return postgresIdentitySession{}, fmt.Errorf("identity session is invalid")
	}
	if err != nil {
		return postgresIdentitySession{}, fmt.Errorf("resolve identity session: %w", err)
	}
	return session, nil
}

func (store *ProductionIdentityStore) sessionDigest(token string) string {
	mac := hmac.New(sha256.New, store.sessionKey)
	_, _ = mac.Write([]byte(token))
	return hex.EncodeToString(mac.Sum(nil))
}

func bearerToken(request *http.Request) (string, error) {
	if request == nil {
		return "", fmt.Errorf("identity session request is required")
	}
	authorization := strings.TrimSpace(request.Header.Get("Authorization"))
	if authorization == "" {
		return "", fmt.Errorf("Bearer identity session is required")
	}
	scheme, token, found := strings.Cut(authorization, " ")
	token = strings.TrimSpace(token)
	if !found || !strings.EqualFold(scheme, "Bearer") || token == "" ||
		len(token) > 4096 || strings.ContainsAny(token, " \t\r\n,") {
		return "", fmt.Errorf("Bearer identity session is malformed")
	}
	return token, nil
}

func (store *ProductionIdentityStore) ResolveIdentityHTTPSession(
	ctx context.Context,
	request *http.Request,
) (IdentityHTTPSession, error) {
	session, err := store.resolveSession(ctx, request)
	if err != nil {
		return IdentityHTTPSession{}, err
	}
	return IdentityHTTPSession{
		AccountID: session.AccountID,
		ActorID:   session.ActorID,
		SessionID: session.SessionID,
		Revoked:   session.Revoked,
	}, nil
}

func (store *ProductionIdentityStore) ResolveOAuthSession(
	ctx context.Context,
	request *http.Request,
) (OAuthSession, error) {
	session, err := store.resolveSession(ctx, request)
	if err != nil {
		return OAuthSession{}, err
	}
	return OAuthSession{
		TenantID:  session.TenantID,
		UserID:    session.UserID,
		SessionID: session.SessionID,
		AccountID: session.AccountID,
		Revoked:   session.Revoked,
	}, nil
}

func (store *ProductionIdentityStore) ResolveGitHubOAuthSession(
	ctx context.Context,
	request *http.Request,
) (GitHubOAuthSession, error) {
	session, err := store.resolveSession(ctx, request)
	if err != nil {
		return GitHubOAuthSession{}, err
	}
	return GitHubOAuthSession{
		TenantID:  session.TenantID,
		UserID:    session.UserID,
		SessionID: session.SessionID,
		AccountID: session.AccountID,
		Revoked:   session.Revoked,
	}, nil
}

var (
	_ IdentityHTTPSessionResolver = (*ProductionIdentityStore)(nil)
	_ OAuthSessionResolver        = (*ProductionIdentityStore)(nil)
	_ GitHubOAuthSessionResolver  = (*ProductionIdentityStore)(nil)
)
