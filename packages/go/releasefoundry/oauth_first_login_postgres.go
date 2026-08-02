package releasefoundry

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"
	"unicode"

	"github.com/lib/pq"
)

const (
	maxPostgresOAuthFirstLoginAttempts       = 8
	maxPostgresOAuthFirstLoginCompletionAge  = 30 * time.Minute
	maxPostgresOAuthFirstLoginCompletionSkew = 5 * time.Minute
	maxPostgresOAuthFirstLoginLookupDigests  = 16
)

const postgresOAuthFirstLoginCompletionQuery = `
SELECT
  session_id::text,
  principal_id::text,
  credential_id::text,
  connection_id::text,
  token_ref_id::text,
  created,
  organization_id::text,
  project_id::text,
  provider_name,
  access_expires_at,
  refresh_expires_at,
  completed_at
FROM a1_complete_oauth_first_login_with_refresh(
  $1::uuid,
  $2::uuid,
  $3,
  $4::text[],
  $5::text[],
  $6,
  $7,
  $8,
  $9,
  $10,
  $11,
  $12,
  $13,
  $14,
  $15,
  $16,
  $17::jsonb
)
`

// PostgresOAuthFirstLoginCoordinatorOptions binds first-login completion to
// one trusted organization/project scope. Browser/provider input cannot select
// a different tenant boundary.
type PostgresOAuthFirstLoginCoordinatorOptions struct {
	Store          *ProductionIdentityStore
	OrganizationID string
	ProjectID      string
	AccessTTL      time.Duration
	RefreshTTL     time.Duration
}

// PostgresOAuthFirstLoginCoordinator is the production adapter between the
// provider-verified first-login flow and migration 026. It never receives an
// OAuth authorization code, state, PKCE verifier, nonce, provider token, or
// browser cookie.
type PostgresOAuthFirstLoginCoordinator struct {
	store          *ProductionIdentityStore
	organizationID string
	projectID      string
	accessTTL      time.Duration
	refreshTTL     time.Duration
}

type postgresOAuthFirstLoginMaterial struct {
	command              OAuthFirstLoginCompletionCommand
	subjectDigests       []string
	emailDigests         []string
	accessToken          identitySessionTokenMaterial
	refreshToken         identitySessionTokenMaterial
	opaqueRefDigest      string
	bindingDigest        string
	rotationFamilyDigest string
	idempotencyDigest    string
	requestDigest        string
	accessExpiresAt      time.Time
	refreshExpiresAt     time.Time
	metadata             []byte
}

type postgresOAuthFirstLoginCompletionRow struct {
	sessionID        string
	principalID      string
	credentialID     string
	connectionID     string
	tokenRefID       string
	created          bool
	organizationID   string
	projectID        string
	provider         string
	accessExpiresAt  time.Time
	refreshExpiresAt time.Time
	completedAt      time.Time
}

func NewPostgresOAuthFirstLoginCoordinator(
	options PostgresOAuthFirstLoginCoordinatorOptions,
) (*PostgresOAuthFirstLoginCoordinator, error) {
	store := options.Store
	if store == nil || store.db == nil || store.sessionTokens == nil ||
		store.lifecycleKeys == nil || store.now == nil {
		return nil, fmt.Errorf(
			"postgres OAuth first-login coordinator requires one production identity database and session/lookup keyrings",
		)
	}
	organizationID := strings.TrimSpace(options.OrganizationID)
	projectID := strings.TrimSpace(options.ProjectID)
	if organizationID != options.OrganizationID ||
		projectID != options.ProjectID ||
		!validPostgresIdentityVerificationUUID(organizationID) ||
		!validPostgresIdentityVerificationUUID(projectID) {
		return nil, fmt.Errorf(
			"postgres OAuth first-login trusted scope must use canonical UUIDs",
		)
	}
	accessTTL := options.AccessTTL
	if accessTTL == 0 {
		accessTTL = defaultIdentityAccessSessionTTL
	}
	refreshTTL := options.RefreshTTL
	if refreshTTL == 0 {
		refreshTTL = defaultIdentityRefreshSessionTTL
	}
	if accessTTL < time.Minute || accessTTL > 7*24*time.Hour ||
		refreshTTL <= accessTTL || refreshTTL > 366*24*time.Hour {
		return nil, fmt.Errorf(
			"postgres OAuth first-login lifetimes must satisfy 1m <= access <= 7d < refresh <= 366d",
		)
	}
	if count := postgresOAuthFirstLoginLookupKeyCount(store.lifecycleKeys); count < 1 ||
		count > maxPostgresOAuthFirstLoginLookupDigests {
		return nil, fmt.Errorf(
			"postgres OAuth first-login lookup keyring must contain between 1 and %d keys",
			maxPostgresOAuthFirstLoginLookupDigests,
		)
	}
	return &PostgresOAuthFirstLoginCoordinator{
		store:          store,
		organizationID: organizationID,
		projectID:      projectID,
		accessTTL:      accessTTL,
		refreshTTL:     refreshTTL,
	}, nil
}

func (coordinator *PostgresOAuthFirstLoginCoordinator) CompleteOAuthFirstLogin(
	ctx context.Context,
	command OAuthFirstLoginCompletionCommand,
) (OAuthFirstLoginCompletionResult, IdentitySessionIssuanceReceipt, error) {
	if coordinator == nil || coordinator.store == nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			postgresOAuthFirstLoginUnavailable()
	}
	if ctx == nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			postgresOAuthFirstLoginUnavailable()
	}
	if err := coordinator.validateCommand(command); err != nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{}, err
	}
	material, err := coordinator.prepareMaterial(command)
	if err != nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			postgresOAuthFirstLoginUnavailable()
	}
	clearBearers := func() {
		material.accessToken.bearer = ""
		material.refreshToken.bearer = ""
	}
	handoffComplete := false
	defer func() {
		if !handoffComplete {
			clearBearers()
		}
	}()

	var row postgresOAuthFirstLoginCompletionRow
	for attempt := 0; attempt < maxPostgresOAuthFirstLoginAttempts; attempt++ {
		row, err = coordinator.completeOnce(ctx, material)
		if !isPostgresTransactionRetryable(err) {
			break
		}
		timer := time.NewTimer(time.Duration(attempt+1) * 5 * time.Millisecond)
		select {
		case <-ctx.Done():
			timer.Stop()
			err = ctx.Err()
			attempt = maxPostgresOAuthFirstLoginAttempts
		case <-timer.C:
		}
	}
	if err != nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			mapPostgresOAuthFirstLoginError(err)
	}
	if err = coordinator.validateCompletionRow(material, row); err != nil {
		return OAuthFirstLoginCompletionResult{}, IdentitySessionIssuanceReceipt{},
			postgresOAuthFirstLoginUnavailable()
	}

	receipt := newIdentitySessionIssuanceReceiptWithRefresh(
		row.sessionID,
		material.accessToken.keyVersion,
		material.refreshToken.keyVersion,
		row.accessExpiresAt.UTC(),
		row.refreshExpiresAt.UTC(),
		material.accessToken.bearer,
		material.refreshToken.bearer,
	)
	result := OAuthFirstLoginCompletionResult{
		SchemaVersion: OAuthFirstLoginSchemaVersion,
		Provider:      row.provider,
		AccountID:     row.principalID,
		CredentialID:  row.credentialID,
		SessionID:     row.sessionID,
		Created:       row.created,
		CompletedAt:   row.completedAt.UTC(),
	}
	clearBearers()
	handoffComplete = true
	return result, receipt, nil
}

func (coordinator *PostgresOAuthFirstLoginCoordinator) completeOnce(
	ctx context.Context,
	material postgresOAuthFirstLoginMaterial,
) (postgresOAuthFirstLoginCompletionRow, error) {
	operationCtx, cancel := context.WithTimeout(ctx, coordinator.store.sqlTimeout)
	defer cancel()
	tx, err := coordinator.store.db.BeginTx(
		operationCtx,
		&sql.TxOptions{Isolation: sql.LevelSerializable},
	)
	if err != nil {
		return postgresOAuthFirstLoginCompletionRow{}, err
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if err = configureIdentityLifecycleTx(
		operationCtx,
		tx,
		coordinator.store.statementTimeout,
		coordinator.store.lockTimeout,
	); err != nil {
		return postgresOAuthFirstLoginCompletionRow{}, err
	}
	if _, err = tx.ExecContext(operationCtx, `
SELECT set_config('app.a1_organization_id',$1,true),
       set_config('app.a1_project_id',$2,true)
`, coordinator.organizationID, coordinator.projectID); err != nil {
		return postgresOAuthFirstLoginCompletionRow{}, err
	}

	var row postgresOAuthFirstLoginCompletionRow
	err = tx.QueryRowContext(
		operationCtx,
		postgresOAuthFirstLoginCompletionQuery,
		coordinator.organizationID,
		coordinator.projectID,
		material.command.Provider,
		pq.Array(material.subjectDigests),
		pq.Array(material.emailDigests),
		material.command.TokenRef,
		material.opaqueRefDigest,
		material.bindingDigest,
		material.accessToken.digest,
		material.refreshToken.digest,
		material.rotationFamilyDigest,
		material.accessExpiresAt,
		material.refreshExpiresAt,
		material.idempotencyDigest,
		material.requestDigest,
		material.command.DisplayName,
		string(material.metadata),
	).Scan(
		&row.sessionID,
		&row.principalID,
		&row.credentialID,
		&row.connectionID,
		&row.tokenRefID,
		&row.created,
		&row.organizationID,
		&row.projectID,
		&row.provider,
		&row.accessExpiresAt,
		&row.refreshExpiresAt,
		&row.completedAt,
	)
	if err != nil {
		return postgresOAuthFirstLoginCompletionRow{}, err
	}
	if err = coordinator.validateCompletionRow(material, row); err != nil {
		return postgresOAuthFirstLoginCompletionRow{}, err
	}
	if err = tx.Commit(); err != nil {
		return postgresOAuthFirstLoginCompletionRow{}, err
	}
	committed = true
	return row, nil
}

func (coordinator *PostgresOAuthFirstLoginCoordinator) validateCommand(
	command OAuthFirstLoginCompletionCommand,
) error {
	if command.SchemaVersion != OAuthFirstLoginSchemaVersion ||
		command.Purpose != OAuthPurposeFirstLogin ||
		command.OrganizationID != coordinator.organizationID ||
		command.ProjectID != coordinator.projectID ||
		!validPostgresIdentityVerificationUUID(command.OrganizationID) ||
		!validPostgresIdentityVerificationUUID(command.ProjectID) {
		return postgresOAuthFirstLoginInvalid()
	}
	if command.Provider != "google" && command.Provider != "github" {
		return postgresOAuthFirstLoginInvalid()
	}
	if !validOAuthFirstLoginHandle(command.ProviderSubject, 1024) ||
		strings.IndexFunc(command.ProviderSubject, unicode.IsControl) >= 0 {
		return postgresOAuthFirstLoginInvalid()
	}
	if command.VerifiedEmail != "" {
		if len(command.VerifiedEmail) > 320 {
			return postgresOAuthFirstLoginInvalid()
		}
		normalized, err := normalizeIdentityEmail(command.VerifiedEmail)
		if err != nil || normalized != command.VerifiedEmail {
			return postgresOAuthFirstLoginInvalid()
		}
	}
	if command.TokenRef != strings.TrimSpace(command.TokenRef) ||
		!isOAuthOpaqueReference(command.TokenRef) ||
		strings.IndexFunc(command.TokenRef, unicode.IsControl) >= 0 {
		return postgresOAuthFirstLoginInvalid()
	}
	if command.DisplayName != strings.TrimSpace(command.DisplayName) ||
		len(command.DisplayName) > 256 ||
		strings.IndexFunc(command.DisplayName, unicode.IsControl) >= 0 {
		return postgresOAuthFirstLoginInvalid()
	}
	if command.CompletedAt.IsZero() ||
		command.CompletedAt.Location() != time.UTC {
		return postgresOAuthFirstLoginInvalid()
	}
	now := coordinator.store.now().UTC()
	if command.CompletedAt.Before(
		now.Add(-maxPostgresOAuthFirstLoginCompletionAge),
	) || command.CompletedAt.After(
		now.Add(maxPostgresOAuthFirstLoginCompletionSkew),
	) {
		return postgresOAuthFirstLoginInvalid()
	}
	return nil
}

func (coordinator *PostgresOAuthFirstLoginCoordinator) prepareMaterial(
	command OAuthFirstLoginCompletionCommand,
) (postgresOAuthFirstLoginMaterial, error) {
	accessToken, err := coordinator.store.sessionTokens.issue()
	if err != nil {
		return postgresOAuthFirstLoginMaterial{}, err
	}
	refreshToken, err := coordinator.store.sessionTokens.issueRefresh()
	if err != nil {
		accessToken.bearer = ""
		return postgresOAuthFirstLoginMaterial{}, err
	}
	clearBearers := func() {
		accessToken.bearer = ""
		refreshToken.bearer = ""
	}
	if accessToken.keyVersion != refreshToken.keyVersion {
		clearBearers()
		return postgresOAuthFirstLoginMaterial{}, errors.New(
			"OAuth first-login session key versions diverged",
		)
	}

	subjectMaterial := strings.Join([]string{
		"oauth-first-login",
		"provider-subject",
		command.Provider,
		command.ProviderSubject,
	}, "\x00")
	subjectDigests := coordinator.store.lifecycleKeys.receiptDigests(subjectMaterial)
	if len(subjectDigests) < 1 ||
		len(subjectDigests) > maxPostgresOAuthFirstLoginLookupDigests {
		clearBearers()
		return postgresOAuthFirstLoginMaterial{}, errors.New(
			"OAuth first-login subject lookup keyring is unavailable",
		)
	}
	emailDigests := []string{}
	if command.VerifiedEmail != "" {
		emailDigests = coordinator.store.lifecycleKeys.receiptDigests(
			strings.Join([]string{
				"oauth-first-login",
				"verified-email",
				command.VerifiedEmail,
			}, "\x00"),
		)
		if len(emailDigests) < 1 ||
			len(emailDigests) > maxPostgresOAuthFirstLoginLookupDigests {
			clearBearers()
			return postgresOAuthFirstLoginMaterial{}, errors.New(
				"OAuth first-login email lookup keyring is unavailable",
			)
		}
	}

	accessExpiresAt := command.CompletedAt.Add(coordinator.accessTTL).
		UTC().Truncate(time.Microsecond)
	refreshExpiresAt := command.CompletedAt.Add(coordinator.refreshTTL).
		UTC().Truncate(time.Microsecond)
	digest := coordinator.store.lifecycleKeys.receiptDigest
	opaqueRefDigest := digest(strings.Join([]string{
		"oauth-first-login",
		"opaque-reference",
		coordinator.organizationID,
		coordinator.projectID,
		command.Provider,
		command.TokenRef,
	}, "\x00"))
	bindingDigest := digest(strings.Join([]string{
		"oauth-first-login",
		"binding",
		coordinator.organizationID,
		coordinator.projectID,
		command.Provider,
		subjectDigests[0],
		command.TokenRef,
	}, "\x00"))
	rotationFamilyDigest, err := coordinator.store.sessionTokens.digestActive(
		"oauth-first-login",
		"rotation-family",
		coordinator.organizationID,
		coordinator.projectID,
		command.Provider,
		subjectDigests[0],
		accessToken.digest,
		refreshToken.digest,
	)
	if err != nil {
		clearBearers()
		return postgresOAuthFirstLoginMaterial{}, err
	}
	idempotencyDigest := digest(strings.Join([]string{
		"oauth-first-login",
		"idempotency",
		coordinator.organizationID,
		coordinator.projectID,
		command.Provider,
		subjectDigests[0],
		command.TokenRef,
		accessToken.digest,
		refreshToken.digest,
	}, "\x00"))
	requestDigest := digest(strings.Join([]string{
		"oauth-first-login",
		"request",
		command.SchemaVersion,
		string(command.Purpose),
		coordinator.organizationID,
		coordinator.projectID,
		command.Provider,
		subjectDigests[0],
		firstPostgresOAuthFirstLoginDigest(emailDigests),
		opaqueRefDigest,
		bindingDigest,
		accessToken.digest,
		refreshToken.digest,
		rotationFamilyDigest,
		accessExpiresAt.Format(time.RFC3339Nano),
		refreshExpiresAt.Format(time.RFC3339Nano),
		command.DisplayName,
	}, "\x00"))
	metadata, err := json.Marshal(map[string]string{
		"source":              "oauth_first_login",
		"provider":            command.Provider,
		"session_key_version": accessToken.keyVersion,
		"identity_lookup_key_version": postgresOAuthFirstLoginLookupKeyVersion(
			coordinator.store.lifecycleKeys,
		),
	})
	if err != nil || len(metadata) > 8192 {
		clearBearers()
		return postgresOAuthFirstLoginMaterial{}, errors.New(
			"OAuth first-login metadata is unavailable",
		)
	}
	return postgresOAuthFirstLoginMaterial{
		command:              command,
		subjectDigests:       subjectDigests,
		emailDigests:         emailDigests,
		accessToken:          accessToken,
		refreshToken:         refreshToken,
		opaqueRefDigest:      opaqueRefDigest,
		bindingDigest:        bindingDigest,
		rotationFamilyDigest: rotationFamilyDigest,
		idempotencyDigest:    idempotencyDigest,
		requestDigest:        requestDigest,
		accessExpiresAt:      accessExpiresAt,
		refreshExpiresAt:     refreshExpiresAt,
		metadata:             metadata,
	}, nil
}

func (coordinator *PostgresOAuthFirstLoginCoordinator) validateCompletionRow(
	material postgresOAuthFirstLoginMaterial,
	row postgresOAuthFirstLoginCompletionRow,
) error {
	if !validPostgresIdentityVerificationUUID(row.sessionID) ||
		!validPostgresIdentityVerificationUUID(row.principalID) ||
		!validPostgresIdentityVerificationUUID(row.credentialID) ||
		!validPostgresIdentityVerificationUUID(row.connectionID) ||
		!validPostgresIdentityVerificationUUID(row.tokenRefID) ||
		row.organizationID != coordinator.organizationID ||
		row.projectID != coordinator.projectID ||
		row.provider != material.command.Provider ||
		!row.accessExpiresAt.UTC().Equal(material.accessExpiresAt) ||
		!row.refreshExpiresAt.UTC().Equal(material.refreshExpiresAt) ||
		row.completedAt.IsZero() ||
		!row.completedAt.UTC().Before(row.accessExpiresAt.UTC()) ||
		!row.accessExpiresAt.UTC().Before(row.refreshExpiresAt.UTC()) ||
		row.completedAt.UTC().Before(
			material.command.CompletedAt.Add(-maxPostgresOAuthFirstLoginCompletionSkew),
		) ||
		row.completedAt.UTC().After(
			coordinator.store.now().UTC().Add(
				maxPostgresOAuthFirstLoginCompletionSkew,
			),
		) {
		return errors.New("OAuth first-login completion result is invalid")
	}
	return nil
}

func mapPostgresOAuthFirstLoginError(err error) error {
	if err == nil {
		return nil
	}
	var postgresError *pq.Error
	if errors.As(err, &postgresError) {
		message := strings.ToLower(postgresError.Message)
		switch string(postgresError.Code) {
		case "23505":
			switch {
			case strings.Contains(message, "canonical_email_conflict"):
				return newOAuthPublicError(
					http.StatusConflict,
					"oauth_first_login_email_conflict",
					"Verified email is already associated with another account",
					nil,
				)
			case strings.Contains(message, "idempotency_conflict"):
				return newOAuthPublicError(
					http.StatusConflict,
					"oauth_first_login_replay_conflict",
					"OAuth first-login replay conflicts with an earlier request",
					nil,
				)
			default:
				return newOAuthPublicError(
					http.StatusConflict,
					"oauth_first_login_conflict",
					"OAuth credential conflicts with an existing account",
					nil,
				)
			}
		case "42501":
			return newOAuthPublicError(
				http.StatusForbidden,
				"oauth_first_login_not_authorized",
				"OAuth first login is not available for this account or project",
				nil,
			)
		case "22023":
			return postgresOAuthFirstLoginInvalid()
		}
	}
	return postgresOAuthFirstLoginUnavailable()
}

func postgresOAuthFirstLoginInvalid() OAuthError {
	return newOAuthPublicError(
		http.StatusBadRequest,
		"oauth_first_login_completion_invalid",
		"OAuth first-login completion is invalid",
		nil,
	)
}

func postgresOAuthFirstLoginUnavailable() OAuthError {
	return newOAuthPublicError(
		http.StatusServiceUnavailable,
		"oauth_first_login_unavailable",
		"OAuth first login is temporarily unavailable",
		nil,
	)
}

func postgresOAuthFirstLoginLookupKeyCount(
	ring *identityLifecycleKeyring,
) int {
	if ring == nil {
		return 0
	}
	ring.mu.RLock()
	defer ring.mu.RUnlock()
	return len(ring.lookupKeys)
}

func postgresOAuthFirstLoginLookupKeyVersion(
	ring *identityLifecycleKeyring,
) string {
	if ring == nil {
		return ""
	}
	ring.mu.RLock()
	defer ring.mu.RUnlock()
	return ring.lookupActive
}

func firstPostgresOAuthFirstLoginDigest(digests []string) string {
	if len(digests) == 0 {
		return ""
	}
	return digests[0]
}

var _ OAuthFirstLoginCoordinator = (*PostgresOAuthFirstLoginCoordinator)(nil)
