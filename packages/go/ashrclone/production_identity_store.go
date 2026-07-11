package ashrclone

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	_ "github.com/lib/pq"
)

const (
	IdentityRuntimePostgres = "postgres"
	IdentityRuntimeMemory   = "memory"
)

const (
	defaultIdentitySessionKeyVersion = "v1"
	identitySessionBearerPrefix      = "ashr_session"
	identityRefreshBearerPrefix      = "ashr_refresh"
	identitySessionNonceBytes        = 32
)

const productionIdentityReadinessQuery = `
SELECT to_regclass('public.identity_principals') IS NOT NULL
   AND to_regclass('public.identity_credentials') IS NOT NULL
   AND to_regclass('public.identity_sessions') IS NOT NULL
   AND to_regclass('public.oauth_runtime_transactions') IS NOT NULL
   AND to_regclass('public.oauth_account_connections') IS NOT NULL
   AND to_regclass('public.oauth_revocation_outbox') IS NOT NULL
   AND to_regclass('public.identity_verification_challenges') IS NOT NULL
   AND to_regclass('public.identity_verification_receipts') IS NOT NULL
   AND to_regclass('public.identity_verification_delivery_outbox') IS NOT NULL
   AND to_regclass('public.identity_verification_abuse_budgets') IS NOT NULL
   AND to_regclass('public.identity_verification_audit_events') IS NOT NULL
   AND to_regclass('public.identity_session_lifecycle_operations') IS NOT NULL
   AND to_regclass('public.identity_verification_delivery_redrive_audit') IS NOT NULL
   AND to_regprocedure(
     'public.a1_complete_oauth_identity_callback(uuid,uuid,uuid,text,text,text,text,text,text,text,text,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_disconnect_oauth_identity_credential(uuid,uuid,uuid,uuid,uuid,text,text,text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_authenticate_identity_session_digest(text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_issue_identity_verification_challenge_with_delivery(uuid,uuid,uuid,text,text,text,text,text,text,timestamp with time zone,integer,integer,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_verify_identity_verification_attempt(uuid,uuid,text,text,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_bind_verified_identity_credential(uuid,uuid,text,uuid,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_assert_recent_identity_authentication(uuid,uuid,uuid,text,integer,text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_issue_identity_session_with_refresh(uuid,uuid,uuid,uuid,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_rotate_identity_session_refresh(uuid,uuid,uuid,text,bigint,text,text,timestamp with time zone,timestamp with time zone,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_rotate_identity_session_refresh_from_digest(uuid,uuid,text,text,text,timestamp with time zone,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_revoke_identity_session(uuid,uuid,uuid,text,uuid,bigint,integer,text,text,text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_revoke_all_identity_sessions(uuid,uuid,uuid,text,boolean,integer,text,text,text)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_login_with_verified_identity_with_refresh(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_recover_verified_identity_with_refresh(uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_claim_identity_delivery_outbox(uuid,uuid,text,integer,bigint,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_heartbeat_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,bigint,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_complete_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,text,timestamp with time zone,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_retry_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,text,timestamp with time zone,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_dead_letter_identity_delivery_outbox(uuid,uuid,uuid,text,bigint,text,timestamp with time zone)'
   ) IS NOT NULL
   AND to_regprocedure(
     'public.a1_redrive_identity_delivery_outbox(uuid,uuid,uuid,bigint,text,text,text,timestamp with time zone)'
   ) IS NOT NULL
`

type ProductionIdentityStore struct {
	db            *sql.DB
	sessionTokens *identitySessionTokenCodec
	now           func() time.Time
}

type IdentitySessionHMACKey struct {
	Version string
	Key     []byte
}

type ProductionIdentityStoreOptions struct {
	DB                      *sql.DB
	SessionKey              []byte
	SessionKeyVersion       string
	PreviousSessionKeys     []IdentitySessionHMACKey
	LegacySessionKeyVersion string
	Random                  io.Reader
	Now                     func() time.Time
}

type identitySessionTokenMaterial struct {
	bearer     string
	digest     string
	keyVersion string
}

type identitySessionTokenCodec struct {
	mu            sync.RWMutex
	activeVersion string
	legacyVersion string
	keys          map[string][]byte
	random        io.Reader
}

func newIdentitySessionTokenCodec(options ProductionIdentityStoreOptions) (*identitySessionTokenCodec, error) {
	activeVersion := strings.TrimSpace(options.SessionKeyVersion)
	if activeVersion == "" {
		activeVersion = defaultIdentitySessionKeyVersion
	}
	if !validIdentitySessionKeyVersion(activeVersion) {
		return nil, fmt.Errorf("production identity active session key version is invalid")
	}
	if len(options.SessionKey) < 32 {
		return nil, fmt.Errorf("production identity session HMAC key must contain at least 32 bytes")
	}
	keys := map[string][]byte{
		activeVersion: append([]byte(nil), options.SessionKey...),
	}
	keepKeys := false
	defer func() {
		if !keepKeys {
			zeroIdentitySessionHMACKeys(keys)
		}
	}()
	for _, previous := range options.PreviousSessionKeys {
		version := strings.TrimSpace(previous.Version)
		if !validIdentitySessionKeyVersion(version) {
			return nil, fmt.Errorf("production identity previous session key version is invalid")
		}
		if len(previous.Key) < 32 {
			return nil, fmt.Errorf("production identity previous session HMAC key must contain at least 32 bytes")
		}
		if _, duplicate := keys[version]; duplicate {
			return nil, fmt.Errorf("production identity session key version %q is duplicated", version)
		}
		keys[version] = append([]byte(nil), previous.Key...)
	}
	legacyVersion := strings.TrimSpace(options.LegacySessionKeyVersion)
	if legacyVersion == "" {
		legacyVersion = activeVersion
	}
	if _, ok := keys[legacyVersion]; !ok {
		return nil, fmt.Errorf("production identity legacy session key version is not configured")
	}
	random := options.Random
	if random == nil {
		random = rand.Reader
	}
	keepKeys = true
	return &identitySessionTokenCodec{
		activeVersion: activeVersion,
		legacyVersion: legacyVersion,
		keys:          keys,
		random:        random,
	}, nil
}

func (codec *identitySessionTokenCodec) issue() (identitySessionTokenMaterial, error) {
	return codec.issueWithPrefix(identitySessionBearerPrefix)
}

func (codec *identitySessionTokenCodec) issueRefresh() (identitySessionTokenMaterial, error) {
	return codec.issueWithPrefix(identityRefreshBearerPrefix)
}

func (codec *identitySessionTokenCodec) issueWithPrefix(
	prefix string,
) (identitySessionTokenMaterial, error) {
	if codec == nil {
		return identitySessionTokenMaterial{}, fmt.Errorf("identity session token codec is unavailable")
	}
	if prefix != identitySessionBearerPrefix && prefix != identityRefreshBearerPrefix {
		return identitySessionTokenMaterial{}, fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.Lock()
	defer codec.mu.Unlock()
	key := codec.keys[codec.activeVersion]
	if len(key) < 32 || codec.random == nil {
		return identitySessionTokenMaterial{}, fmt.Errorf("identity session token codec is unavailable")
	}
	nonce := make([]byte, identitySessionNonceBytes)
	if _, err := io.ReadFull(codec.random, nonce); err != nil {
		return identitySessionTokenMaterial{}, fmt.Errorf("generate identity session bearer: %w", err)
	}
	bearer := prefix + "." + codec.activeVersion + "." +
		base64.RawURLEncoding.EncodeToString(nonce)
	return identitySessionTokenMaterial{
		bearer:     bearer,
		digest:     identitySessionHMAC(key, bearer),
		keyVersion: codec.activeVersion,
	}, nil
}

func (codec *identitySessionTokenCodec) digest(bearer string) (string, string, error) {
	if codec == nil {
		return "", "", fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	version, err := codec.keyVersionForBearer(bearer)
	if err != nil {
		return "", "", err
	}
	key := codec.keys[version]
	if len(key) < 32 {
		return "", "", fmt.Errorf("identity session bearer key version is unavailable")
	}
	return identitySessionHMAC(key, bearer), version, nil
}

func (codec *identitySessionTokenCodec) digestRefresh(
	bearer string,
) (string, string, error) {
	if codec == nil {
		return "", "", fmt.Errorf("identity refresh token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	version, err := codec.keyVersionForPrefixedBearer(
		bearer,
		identityRefreshBearerPrefix,
	)
	if err != nil {
		return "", "", err
	}
	key := codec.keys[version]
	if len(key) < 32 {
		return "", "", fmt.Errorf("identity refresh bearer key version is unavailable")
	}
	return identitySessionHMAC(key, bearer), version, nil
}

func (codec *identitySessionTokenCodec) digestActive(parts ...string) (string, error) {
	if codec == nil {
		return "", fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	key := codec.keys[codec.activeVersion]
	if len(key) < 32 {
		return "", fmt.Errorf("identity session token codec is unavailable")
	}
	return identitySessionHMAC(key, strings.Join(parts, "\x00")), nil
}

func (codec *identitySessionTokenCodec) digestWithVersion(
	version string,
	parts ...string,
) (string, error) {
	if codec == nil || !validIdentitySessionKeyVersion(version) {
		return "", fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	key := codec.keys[version]
	if len(key) < 32 {
		return "", fmt.Errorf("identity session token codec is unavailable")
	}
	return identitySessionHMAC(key, strings.Join(parts, "\x00")), nil
}

func (codec *identitySessionTokenCodec) deriveRefreshRotation(
	refreshBearer string,
	idempotencyKey string,
) (identitySessionTokenMaterial, identitySessionTokenMaterial, error) {
	if codec == nil {
		return identitySessionTokenMaterial{}, identitySessionTokenMaterial{},
			fmt.Errorf("identity session token codec is unavailable")
	}
	codec.mu.RLock()
	defer codec.mu.RUnlock()
	refreshKeyVersion, err := codec.keyVersionForPrefixedBearer(
		refreshBearer, identityRefreshBearerPrefix,
	)
	if err != nil {
		return identitySessionTokenMaterial{}, identitySessionTokenMaterial{}, err
	}
	key := codec.keys[refreshKeyVersion]
	if len(key) < 32 || !validIdentitySessionIdempotencyKey(idempotencyKey) {
		return identitySessionTokenMaterial{}, identitySessionTokenMaterial{},
			fmt.Errorf("identity session token codec is unavailable")
	}
	derive := func(label string, prefix string) identitySessionTokenMaterial {
		nonce := identitySessionHMACBytes(
			key,
			strings.Join([]string{
				"identity-refresh-rotation",
				label,
				refreshBearer,
				idempotencyKey,
			}, "\x00"),
		)
		bearer := prefix + "." + refreshKeyVersion + "." +
			base64.RawURLEncoding.EncodeToString(nonce)
		return identitySessionTokenMaterial{
			bearer:     bearer,
			digest:     identitySessionHMAC(key, bearer),
			keyVersion: refreshKeyVersion,
		}
	}
	return derive("access", identitySessionBearerPrefix),
		derive("refresh", identityRefreshBearerPrefix), nil
}

func (codec *identitySessionTokenCodec) keyVersionForBearer(bearer string) (string, error) {
	if strings.HasPrefix(bearer, identityRefreshBearerPrefix+".") {
		return "", fmt.Errorf("identity session bearer is malformed")
	}
	prefix := identitySessionBearerPrefix + "."
	if !strings.HasPrefix(bearer, prefix) {
		return codec.legacyVersion, nil
	}
	return codec.keyVersionForPrefixedBearer(bearer, identitySessionBearerPrefix)
}

func (codec *identitySessionTokenCodec) keyVersionForPrefixedBearer(
	bearer string,
	prefix string,
) (string, error) {
	parts := strings.Split(bearer, ".")
	if len(parts) != 3 || parts[0] != prefix ||
		!validIdentitySessionKeyVersion(parts[1]) {
		return "", fmt.Errorf("identity session bearer is malformed")
	}
	nonce, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil || len(nonce) != identitySessionNonceBytes {
		return "", fmt.Errorf("identity session bearer is malformed")
	}
	if _, ok := codec.keys[parts[1]]; !ok {
		return "", fmt.Errorf("identity session bearer key version is unavailable")
	}
	return parts[1], nil
}

func (codec *identitySessionTokenCodec) close() {
	if codec == nil {
		return
	}
	codec.mu.Lock()
	defer codec.mu.Unlock()
	zeroIdentitySessionHMACKeys(codec.keys)
}

func zeroIdentitySessionHMACKeys(keys map[string][]byte) {
	for version, key := range keys {
		for index := range key {
			key[index] = 0
		}
		delete(keys, version)
	}
}

func identitySessionHMAC(key []byte, bearer string) string {
	return hex.EncodeToString(identitySessionHMACBytes(key, bearer))
}

func identitySessionHMACBytes(key []byte, bearer string) []byte {
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(bearer))
	return mac.Sum(nil)
}

func validIdentitySessionKeyVersion(version string) bool {
	if len(version) < 1 || len(version) > 32 {
		return false
	}
	for _, character := range version {
		if (character < 'a' || character > 'z') &&
			(character < 'A' || character > 'Z') &&
			(character < '0' || character > '9') &&
			character != '_' && character != '-' {
			return false
		}
	}
	return true
}

func NewProductionIdentityStore(options ProductionIdentityStoreOptions) (*ProductionIdentityStore, error) {
	if options.DB == nil {
		return nil, fmt.Errorf("production identity postgres db is required")
	}
	sessionTokens, err := newIdentitySessionTokenCodec(options)
	if err != nil {
		return nil, err
	}
	now := options.Now
	if now == nil {
		now = time.Now
	}
	return &ProductionIdentityStore{
		db:            options.DB,
		sessionTokens: sessionTokens,
		now:           now,
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
	if store == nil {
		return nil
	}
	store.sessionTokens.close()
	if store.db == nil {
		return nil
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
		return fmt.Errorf("production identity PostgreSQL schema is incomplete; migrations 007-015 are required")
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

func (store *ProductionIdentityStore) NewIdentityVerificationStore(
	options PostgresIdentityVerificationStoreOptions,
) (*PostgresIdentityVerificationStore, error) {
	if store == nil || store.db == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	options.DB = store.db
	options.sessionTokens = store.sessionTokens
	return NewPostgresIdentityVerificationStoreWithOptions(options)
}

func (store *ProductionIdentityStore) NewIdentityVerificationTransactionCoordinator(
	verificationStore *PostgresIdentityVerificationStore,
) (*PostgresIdentityVerificationTransactionCoordinator, error) {
	if store == nil || store.db == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	if verificationStore == nil || verificationStore.db != store.db {
		return nil, fmt.Errorf("production identity verification store must belong to the production identity database")
	}
	return NewPostgresIdentityVerificationTransactionCoordinator(verificationStore)
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
	digest, _, err := store.sessionTokens.digest(token)
	if err != nil {
		return postgresIdentitySession{}, fmt.Errorf("identity session is invalid")
	}
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
	if store == nil {
		return ""
	}
	digest, _, err := store.sessionTokens.digest(token)
	if err != nil {
		return ""
	}
	return digest
}

func (store *ProductionIdentityStore) RefreshIdentityHTTPSession(
	ctx context.Context,
	request *http.Request,
	projectID string,
	accountID string,
	idempotencyKey string,
) (IdentitySessionIssuanceReceipt, error) {
	if store == nil || store.db == nil || store.sessionTokens == nil || store.now == nil {
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	projectID = strings.TrimSpace(projectID)
	accountID = strings.TrimSpace(accountID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if !validPostgresIdentityVerificationUUID(projectID) ||
		!validPostgresIdentityVerificationUUID(accountID) ||
		!validIdentitySessionIdempotencyKey(idempotencyKey) {
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	refreshBearer, err := identityRefreshBearerToken(request)
	if err != nil {
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	refreshDigest, refreshKeyVersion, err := store.sessionTokens.digestRefresh(refreshBearer)
	if err != nil {
		refreshBearer = ""
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	accessToken, refreshToken, err := store.sessionTokens.deriveRefreshRotation(
		refreshBearer, idempotencyKey,
	)
	refreshBearer = ""
	if err != nil {
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	clearBearers := func() {
		accessToken.bearer = ""
		refreshToken.bearer = ""
	}
	if accessToken.keyVersion != refreshKeyVersion ||
		refreshToken.keyVersion != refreshKeyVersion {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	now := store.now().UTC()
	requestedAccessExpiresAt := now.Add(defaultIdentityAccessSessionTTL)
	idempotencyDigest, err := store.sessionTokens.digestWithVersion(
		refreshKeyVersion,
		"identity-refresh-idempotency",
		projectID,
		accountID,
		idempotencyKey,
	)
	if err != nil {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	// Access expiry is server policy and may advance between retries. It is not
	// part of the caller's idempotent intent.
	requestDigest, err := store.sessionTokens.digestWithVersion(
		refreshKeyVersion,
		"identity-refresh-request",
		projectID,
		accountID,
		refreshDigest,
		accessToken.digest,
		refreshToken.digest,
	)
	if err != nil {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	var sessionID sql.NullString
	var organizationID, returnedProjectID, principalID string
	var rotationGeneration int64
	var outcomeCode string
	var affectedCount int
	var accessExpiresAt, refreshExpiresAt time.Time
	err = store.db.QueryRowContext(ctx, `
SELECT session_id::text,
       organization_id::text,
       project_id::text,
       principal_id::text,
       rotation_generation,
       outcome_code,
       affected_count,
       access_expires_at,
       refresh_expires_at
  FROM a1_rotate_identity_session_refresh_from_digest(
    $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9::jsonb
  )
`,
		projectID,
		accountID,
		refreshDigest,
		accessToken.digest,
		refreshToken.digest,
		requestedAccessExpiresAt,
		idempotencyDigest,
		requestDigest,
		`{"source":"go_identity_session_refresh_http"}`,
	).Scan(
		&sessionID,
		&organizationID,
		&returnedProjectID,
		&principalID,
		&rotationGeneration,
		&outcomeCode,
		&affectedCount,
		&accessExpiresAt,
		&refreshExpiresAt,
	)
	if err != nil {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	if outcomeCode == "refresh_reuse_detected" {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshReused
	}
	if outcomeCode != "rotated" || !sessionID.Valid ||
		!validPostgresIdentityVerificationUUID(sessionID.String) ||
		!validPostgresIdentityVerificationUUID(organizationID) ||
		returnedProjectID != projectID || principalID != accountID ||
		rotationGeneration < 1 || affectedCount != 1 ||
		!accessExpiresAt.After(now) ||
		!refreshExpiresAt.After(accessExpiresAt) {
		clearBearers()
		return IdentitySessionIssuanceReceipt{}, ErrIdentitySessionRefreshInvalid
	}
	receipt := newIdentitySessionIssuanceReceiptWithRefresh(
		sessionID.String,
		accessToken.keyVersion,
		refreshToken.keyVersion,
		accessExpiresAt.UTC(),
		refreshExpiresAt.UTC(),
		accessToken.bearer,
		refreshToken.bearer,
	)
	clearBearers()
	return receipt, nil
}

func validIdentitySessionIdempotencyKey(value string) bool {
	if len(value) < 8 || len(value) > 256 {
		return false
	}
	for index, character := range value {
		if (character >= 'a' && character <= 'z') ||
			(character >= 'A' && character <= 'Z') ||
			(character >= '0' && character <= '9') ||
			(index > 0 && (character == '.' || character == '_' ||
				character == ':' || character == '-')) {
			continue
		}
		return false
	}
	return true
}

func bearerToken(request *http.Request) (string, error) {
	if request == nil {
		return "", fmt.Errorf("identity session request is required")
	}
	headerValues := request.Header.Values("Authorization")
	if len(headerValues) > 1 {
		return "", fmt.Errorf("identity session credentials are ambiguous")
	}
	headerToken := ""
	if len(headerValues) == 1 {
		authorization := strings.TrimSpace(headerValues[0])
		scheme, token, found := strings.Cut(authorization, " ")
		token = strings.TrimSpace(token)
		if !found || !strings.EqualFold(scheme, "Bearer") ||
			!validIdentitySessionBearerValue(token) {
			return "", fmt.Errorf("Bearer identity session is malformed")
		}
		headerToken = token
	}
	cookieToken, cookiePresent, err := identitySessionCookieBearer(request, IdentitySessionCookieName)
	if err != nil {
		return "", err
	}
	if headerToken == "" && !cookiePresent {
		return "", fmt.Errorf("Bearer identity session is required")
	}
	if headerToken != "" && cookiePresent && headerToken != cookieToken {
		return "", fmt.Errorf("identity session credentials conflict")
	}
	if headerToken != "" {
		return headerToken, nil
	}
	return cookieToken, nil
}

func identityRefreshBearerToken(request *http.Request) (string, error) {
	if request == nil {
		return "", fmt.Errorf("identity refresh request is required")
	}
	if len(request.Header.Values("Authorization")) != 0 {
		return "", fmt.Errorf("identity refresh credentials are ambiguous")
	}
	token, present, err := identitySessionCookieBearer(request, IdentityRefreshCookieName)
	if err != nil {
		return "", err
	}
	if !present {
		return "", fmt.Errorf("identity refresh credential is required")
	}
	return token, nil
}

func identitySessionCookieBearer(
	request *http.Request,
	name string,
) (string, bool, error) {
	var value string
	count := 0
	for _, cookie := range request.Cookies() {
		if cookie.Name != name {
			continue
		}
		count++
		value = cookie.Value
	}
	if count == 0 {
		return "", false, nil
	}
	if count != 1 || !validIdentitySessionBearerValue(value) {
		return "", false, fmt.Errorf("identity session cookie is malformed")
	}
	return value, true, nil
}

func validIdentitySessionBearerValue(value string) bool {
	return value != "" && value == strings.TrimSpace(value) && len(value) <= 4096 &&
		!strings.ContainsAny(value, " \t\r\n,;")
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
	_ IdentityHTTPSessionResolver  = (*ProductionIdentityStore)(nil)
	_ IdentityHTTPSessionRefresher = (*ProductionIdentityStore)(nil)
	_ OAuthSessionResolver         = (*ProductionIdentityStore)(nil)
	_ GitHubOAuthSessionResolver   = (*ProductionIdentityStore)(nil)
)
