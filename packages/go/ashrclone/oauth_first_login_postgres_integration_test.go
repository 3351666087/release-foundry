package ashrclone

import (
	"context"
	"database/sql"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"reflect"
	"strings"
	"testing"
	"time"
)

const oauthFirstLoginPostgresIntegrationFlag = "ASHR_RUN_OAUTH_FIRST_LOGIN_POSTGRES_INTEGRATION"

type oauthFirstLoginDatabaseSnapshot map[string]int64

type oauthFirstLoginForbiddenMaterial struct {
	label string
	value string
}

func TestOAuthFirstLoginPostgresIntegration(t *testing.T) {
	if os.Getenv(oauthFirstLoginPostgresIntegrationFlag) != "1" {
		t.Skip("set " + oauthFirstLoginPostgresIntegrationFlag + "=1 to run PostgreSQL OAuth first-login integration tests")
	}
	adminDSN := strings.TrimSpace(os.Getenv("ASHR_IDENTITY_LIFECYCLE_TEST_DSN"))
	if adminDSN == "" {
		t.Skip("ASHR_IDENTITY_LIFECYCLE_TEST_DSN is not configured")
	}

	h := newPostgresLifecycleHarness(t, adminDSN)

	t.Run("unknown subject registration, browser session handoff, and known subject login", func(t *testing.T) {
		const (
			organizationID = "b1000000-0000-4000-8000-000000000001"
			workspaceID    = "b1000000-0000-4000-8000-000000000002"
			projectID      = "b1000000-0000-4000-8000-000000000003"
		)
		createIdentityVerificationProjectScope(
			t,
			h.adminDB,
			organizationID,
			workspaceID,
			projectID,
			"oauth-first-login-primary",
		)
		instance := h.newInstanceWithLifecycleKeys(
			t,
			[]byte("oauth-first-login-primary-receipt-key-0001"),
			"receipt-primary",
			nil,
			[]byte("oauth-first-login-primary-lookup-key-0001"),
			"lookup-primary",
			nil,
		)
		coordinator := newOAuthFirstLoginIntegrationCoordinator(
			t,
			instance,
			organizationID,
			projectID,
		)

		firstCommand := oauthFirstLoginIntegrationCommand(
			h.now,
			organizationID,
			projectID,
			"google",
			"google-integration-primary-subject",
			"primary-owner@example.cn",
			"vault:oauth-first-login-primary-token-ref-v1",
			"Primary OAuth Owner",
		)
		firstResult, firstReceipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			firstCommand,
		)
		if err != nil {
			t.Fatalf("complete unknown-subject OAuth first login: %v", err)
		}
		if !firstResult.Created ||
			firstResult.SchemaVersion != OAuthFirstLoginSchemaVersion ||
			firstResult.Provider != firstCommand.Provider ||
			firstResult.CompletedAt.IsZero() {
			t.Fatalf("unexpected unknown-subject result: %#v", firstResult)
		}
		if firstReceipt.sessionID != firstResult.SessionID ||
			firstReceipt.keyVersion != "integration" ||
			firstReceipt.refreshKeyVersion != "integration" ||
			!firstReceipt.expiresAt.Before(firstReceipt.refreshExpiresAt) {
			t.Fatalf("unexpected first-login receipt metadata: %#v", firstReceipt)
		}

		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_principals WHERE id=$1::uuid AND status='active'`,
			1,
			firstResult.AccountID,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_credentials
			  WHERE id=$1::uuid
			    AND principal_id=$2::uuid
			    AND provider=$3
			    AND provider_environment='production'
			    AND credential_kind='federated'
			    AND status='active'
			    AND login_enabled`,
			1,
			firstResult.CredentialID,
			firstResult.AccountID,
			firstResult.Provider,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_organization_memberships
			  WHERE organization_id=$1::uuid
			    AND principal_id=$2::uuid
			    AND status='active'`,
			1,
			organizationID,
			firstResult.AccountID,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_project_memberships
			  WHERE organization_id=$1::uuid
			    AND project_id=$2::uuid
			    AND principal_id=$3::uuid
			    AND status='active'`,
			1,
			organizationID,
			projectID,
			firstResult.AccountID,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_account_security
			  WHERE principal_id=$1::uuid
			    AND two_factor_status='disabled'
			    AND two_factor_recommended`,
			1,
			firstResult.AccountID,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_sessions
			  WHERE id=$1::uuid
			    AND principal_id=$2::uuid
			    AND credential_id=$3::uuid
			    AND organization_id=$4::uuid
			    AND project_id=$5::uuid
			    AND status='active'
			    AND refresh_digest IS NOT NULL`,
			1,
			firstResult.SessionID,
			firstResult.AccountID,
			firstResult.CredentialID,
			organizationID,
			projectID,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM oauth_account_connections
			  WHERE organization_id=$1::uuid
			    AND project_id=$2::uuid
			    AND principal_id=$3::uuid
			    AND credential_id=$4::uuid
			    AND provider=$5
			    AND status='active'`,
			1,
			organizationID,
			projectID,
			firstResult.AccountID,
			firstResult.CredentialID,
			firstResult.Provider,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM oauth_first_login_operations
			  WHERE organization_id=$1::uuid
			    AND project_id=$2::uuid
			    AND principal_id=$3::uuid
			    AND credential_id=$4::uuid
			    AND session_id=$5::uuid
			    AND account_created
			    AND status='completed'`,
			1,
			organizationID,
			projectID,
			firstResult.AccountID,
			firstResult.CredentialID,
			firstResult.SessionID,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_audit_events
			  WHERE organization_id=$1::uuid
			    AND project_id=$2::uuid
			    AND principal_id=$3::uuid
			    AND action='identity.oauth.first_login.completed'`,
			1,
			organizationID,
			projectID,
			firstResult.AccountID,
		)

		firstAccessBearer, firstRefreshBearer, err := firstReceipt.TakeBearerTokens()
		if err != nil {
			t.Fatalf("take first-login bearer pair: %v", err)
		}
		if _, _, err := firstReceipt.TakeBearerTokens(); !errors.Is(
			err,
			ErrIdentitySessionBearerTaken,
		) {
			t.Fatalf("first-login bearer pair was not one-use: %v", err)
		}
		firstSession, err := instance.store.ResolveIdentityHTTPSession(
			context.Background(),
			oauthFirstLoginAccessRequest(firstAccessBearer),
		)
		if err != nil {
			t.Fatalf("resolve first-login access bearer: %v", err)
		}
		if firstSession.AccountID != firstResult.AccountID ||
			firstSession.ActorID != firstResult.AccountID ||
			firstSession.SessionID != firstResult.SessionID ||
			firstSession.SessionDigest == "" ||
			firstSession.Revoked {
			t.Fatalf("unexpected first-login session: %#v", firstSession)
		}
		if _, err := instance.store.ResolveIdentityHTTPSession(
			context.Background(),
			oauthFirstLoginAccessRequest(firstRefreshBearer),
		); err == nil {
			t.Fatal("refresh bearer authenticated at the access boundary")
		}

		refreshRequest := httptest.NewRequest(
			http.MethodPost,
			"https://api.example.test/v1/identity/session/refresh",
			nil,
		)
		refreshRequest.AddCookie(&http.Cookie{
			Name:  IdentityRefreshCookieName,
			Value: firstRefreshBearer,
		})
		rotatedReceipt, err := instance.store.RefreshIdentityHTTPSession(
			context.Background(),
			refreshRequest,
			projectID,
			firstResult.AccountID,
			"oauth-first-login-refresh-primary-0001",
		)
		if err != nil {
			t.Fatalf("rotate first-login refresh bearer: %v", err)
		}
		rotatedAccessBearer, rotatedRefreshBearer, err :=
			rotatedReceipt.TakeBearerTokens()
		if err != nil {
			t.Fatalf("take rotated bearer pair: %v", err)
		}
		rotatedSession, err := instance.store.ResolveIdentityHTTPSession(
			context.Background(),
			oauthFirstLoginAccessRequest(rotatedAccessBearer),
		)
		if err != nil {
			t.Fatalf("resolve rotated access bearer: %v", err)
		}
		if rotatedSession.AccountID != firstResult.AccountID ||
			rotatedSession.SessionID != rotatedReceipt.sessionID ||
			rotatedSession.SessionID == firstResult.SessionID {
			t.Fatalf("unexpected rotated session: %#v", rotatedSession)
		}
		if _, err := instance.store.ResolveIdentityHTTPSession(
			context.Background(),
			oauthFirstLoginAccessRequest(firstAccessBearer),
		); err == nil {
			t.Fatal("rotated access bearer remained active")
		}

		beforeKnownLogin := snapshotOAuthFirstLoginDatabase(t, h.adminDB)
		secondCommand := firstCommand
		secondCommand.TokenRef = "vault:oauth-first-login-primary-token-ref-v2"
		secondCommand.DisplayName = "Provider Label Does Not Replace Canonical Account"
		secondResult, secondReceipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			secondCommand,
		)
		if err != nil {
			t.Fatalf("complete known-subject OAuth first login: %v", err)
		}
		if secondResult.Created ||
			secondResult.AccountID != firstResult.AccountID ||
			secondResult.CredentialID != firstResult.CredentialID ||
			secondResult.SessionID == firstResult.SessionID ||
			secondResult.Provider != firstResult.Provider {
			t.Fatalf(
				"known-subject login changed canonical ownership: first=%#v second=%#v",
				firstResult,
				secondResult,
			)
		}
		secondAccessBearer, secondRefreshBearer, err :=
			secondReceipt.TakeBearerTokens()
		if err != nil {
			t.Fatalf("take known-subject bearer pair: %v", err)
		}
		secondSession, err := instance.store.ResolveIdentityHTTPSession(
			context.Background(),
			oauthFirstLoginAccessRequest(secondAccessBearer),
		)
		if err != nil {
			t.Fatalf("resolve known-subject access bearer: %v", err)
		}
		if secondSession.AccountID != firstResult.AccountID ||
			secondSession.SessionID != secondResult.SessionID {
			t.Fatalf("unexpected known-subject session: %#v", secondSession)
		}

		afterKnownLogin := snapshotOAuthFirstLoginDatabase(t, h.adminDB)
		assertOAuthFirstLoginSnapshotDelta(
			t,
			beforeKnownLogin,
			afterKnownLogin,
			map[string]int64{
				"identity_principals":                   0,
				"identity_credentials":                  0,
				"identity_organization_memberships":     0,
				"identity_project_memberships":          0,
				"identity_account_emails":               0,
				"identity_account_security":             0,
				"identity_sessions":                     1,
				"identity_session_lifecycle_operations": 1,
				"oauth_token_opaque_refs":               1,
				"oauth_account_connections":             0,
				"oauth_revocation_outbox":               1,
				"oauth_first_login_operations":          1,
				"identity_audit_events":                 2,
			},
		)
		assertOAuthFirstLoginOpaqueReferenceStatus(
			t,
			h.adminDB,
			firstCommand.TokenRef,
			"revocation_pending",
		)
		assertOAuthFirstLoginOpaqueReferenceStatus(
			t,
			h.adminDB,
			secondCommand.TokenRef,
			"active",
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*)
			   FROM oauth_revocation_outbox AS outbox
			   JOIN oauth_token_opaque_refs AS token_ref
			     ON token_ref.organization_id=outbox.organization_id
			    AND token_ref.project_id=outbox.project_id
			    AND token_ref.id=outbox.token_ref_id
			  WHERE token_ref.opaque_ref=$1
			    AND outbox.provider=$2
			    AND outbox.reason_code='first_login_reauthenticated'
			    AND outbox.status='pending'`,
			1,
			firstCommand.TokenRef,
			firstCommand.Provider,
		)

		assertOAuthFirstLoginNoRawMaterial(
			t,
			h.adminDB,
			[]oauthFirstLoginForbiddenMaterial{
				{label: "provider subject", value: firstCommand.ProviderSubject},
				{label: "verified email", value: firstCommand.VerifiedEmail},
				{label: "initial access bearer", value: firstAccessBearer},
				{label: "initial refresh bearer", value: firstRefreshBearer},
				{label: "rotated access bearer", value: rotatedAccessBearer},
				{label: "rotated refresh bearer", value: rotatedRefreshBearer},
				{label: "known-login access bearer", value: secondAccessBearer},
				{label: "known-login refresh bearer", value: secondRefreshBearer},
			},
		)

		firstAccessBearer = ""
		firstRefreshBearer = ""
		rotatedAccessBearer = ""
		rotatedRefreshBearer = ""
		secondAccessBearer = ""
		secondRefreshBearer = ""
	})

	t.Run("exact transaction replay returns one canonical relation", func(t *testing.T) {
		const (
			organizationID = "b2000000-0000-4000-8000-000000000001"
			workspaceID    = "b2000000-0000-4000-8000-000000000002"
			projectID      = "b2000000-0000-4000-8000-000000000003"
		)
		createIdentityVerificationProjectScope(
			t,
			h.adminDB,
			organizationID,
			workspaceID,
			projectID,
			"oauth-first-login-replay",
		)
		instance := h.newInstanceWithLifecycleKeys(
			t,
			[]byte("oauth-first-login-replay-receipt-key-0001"),
			"receipt-replay",
			nil,
			[]byte("oauth-first-login-replay-lookup-key-0001"),
			"lookup-replay",
			nil,
		)
		coordinator := newOAuthFirstLoginIntegrationCoordinator(
			t,
			instance,
			organizationID,
			projectID,
		)
		command := oauthFirstLoginIntegrationCommand(
			h.now,
			organizationID,
			projectID,
			"github",
			"github-integration-exact-replay-subject",
			"exact-replay@example.cn",
			"vault:oauth-first-login-exact-replay-token-ref",
			"Exact Replay",
		)
		if err := coordinator.validateCommand(command); err != nil {
			t.Fatalf("validate exact replay command: %v", err)
		}
		material, err := coordinator.prepareMaterial(command)
		if err != nil {
			t.Fatalf("prepare exact replay material: %v", err)
		}
		defer func() {
			material.accessToken.bearer = ""
			material.refreshToken.bearer = ""
		}()
		firstRow, err := coordinator.completeOnce(context.Background(), material)
		if err != nil {
			t.Fatalf("complete exact replay first transaction: %v", err)
		}
		secondRow, err := coordinator.completeOnce(context.Background(), material)
		if err != nil {
			t.Fatalf("complete exact replay second transaction: %v", err)
		}
		if firstRow != secondRow || !firstRow.created {
			t.Fatalf(
				"exact replay did not return one canonical relation: first=%#v second=%#v",
				firstRow,
				secondRow,
			)
		}
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM oauth_first_login_operations
			  WHERE organization_id=$1::uuid
			    AND project_id=$2::uuid
			    AND provider=$3
			    AND idempotency_digest=$4
			    AND request_digest=$5
			    AND session_id=$6::uuid
			    AND status='completed'`,
			1,
			organizationID,
			projectID,
			command.Provider,
			material.idempotencyDigest,
			material.requestDigest,
			firstRow.sessionID,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_principals WHERE id=$1::uuid`,
			1,
			firstRow.principalID,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_credentials WHERE id=$1::uuid`,
			1,
			firstRow.credentialID,
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM identity_sessions WHERE id=$1::uuid`,
			1,
			firstRow.sessionID,
		)
		assertOAuthFirstLoginNoRawMaterial(
			t,
			h.adminDB,
			[]oauthFirstLoginForbiddenMaterial{
				{label: "provider subject", value: command.ProviderSubject},
				{label: "verified email", value: command.VerifiedEmail},
				{label: "access bearer", value: material.accessToken.bearer},
				{label: "refresh bearer", value: material.refreshToken.bearer},
			},
		)
	})

	t.Run("verified email conflict rolls back every first-login mutation", func(t *testing.T) {
		const (
			organizationID = "b3000000-0000-4000-8000-000000000001"
			workspaceID    = "b3000000-0000-4000-8000-000000000002"
			projectID      = "b3000000-0000-4000-8000-000000000003"
			emailOwnerID   = "b3000000-0000-4000-8000-000000000004"
		)
		createIdentityVerificationProjectScope(
			t,
			h.adminDB,
			organizationID,
			workspaceID,
			projectID,
			"oauth-first-login-conflict",
		)
		instance := h.newInstanceWithLifecycleKeys(
			t,
			[]byte("oauth-first-login-conflict-receipt-key-01"),
			"receipt-conflict",
			nil,
			[]byte("oauth-first-login-conflict-lookup-key-01"),
			"lookup-conflict",
			nil,
		)
		coordinator := newOAuthFirstLoginIntegrationCoordinator(
			t,
			instance,
			organizationID,
			projectID,
		)
		command := oauthFirstLoginIntegrationCommand(
			h.now,
			organizationID,
			projectID,
			"google",
			"google-integration-conflicting-subject",
			"already-owned@example.cn",
			"vault:oauth-first-login-conflicting-token-ref",
			"Must Roll Back",
		)
		emailDigests := coordinator.store.lifecycleKeys.receiptDigests(
			strings.Join(
				[]string{
					"oauth-first-login",
					"verified-email",
					command.VerifiedEmail,
				},
				"\x00",
			),
		)
		if len(emailDigests) != 1 {
			t.Fatalf("unexpected conflict email digest candidates: %d", len(emailDigests))
		}
		mustExecArgs(t, h.adminDB, `
INSERT INTO identity_principals(
  id,status,display_label,metadata,created_at,updated_at
) VALUES (
  $1::uuid,'active','Existing Email Owner','{}'::jsonb,$2,$2
)
`, emailOwnerID, h.now)
		mustExecArgs(t, h.adminDB, `
INSERT INTO identity_account_emails(
  principal_id,normalized_email_digest,source_provider,verified_at,created_at,updated_at
) VALUES (
  $1::uuid,$2,'email',$3,$3,$3
)
`, emailOwnerID, emailDigests[0], h.now)

		before := snapshotOAuthFirstLoginDatabase(t, h.adminDB)
		result, receipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			command,
		)
		var oauthError OAuthError
		if !errors.As(err, &oauthError) ||
			oauthError.Status != http.StatusConflict ||
			oauthError.Code != "oauth_first_login_email_conflict" ||
			oauthError.Cause != nil {
			t.Fatalf("unexpected verified-email conflict: %#v", err)
		}
		if result != (OAuthFirstLoginCompletionResult{}) ||
			receipt.secret != nil {
			t.Fatalf(
				"verified-email conflict returned a session handoff: result=%#v receipt=%#v",
				result,
				receipt,
			)
		}
		if strings.Contains(err.Error(), command.ProviderSubject) ||
			strings.Contains(err.Error(), command.VerifiedEmail) ||
			strings.Contains(err.Error(), command.TokenRef) {
			t.Fatal("verified-email conflict disclosed private callback material")
		}
		after := snapshotOAuthFirstLoginDatabase(t, h.adminDB)
		if !reflect.DeepEqual(before, after) {
			t.Fatalf(
				"verified-email conflict left partial mutations: before=%v after=%v",
				before,
				after,
			)
		}
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM oauth_token_opaque_refs WHERE opaque_ref=$1`,
			0,
			command.TokenRef,
		)
		assertOAuthFirstLoginNoRawMaterial(
			t,
			h.adminDB,
			[]oauthFirstLoginForbiddenMaterial{
				{label: "conflicting provider subject", value: command.ProviderSubject},
				{label: "conflicting verified email", value: command.VerifiedEmail},
			},
		)
	})

	t.Run("trusted scope and runtime RLS boundaries fail closed", func(t *testing.T) {
		const (
			missingOrganizationID = "b5000000-0000-4000-8000-000000000001"
			missingProjectID      = "b5000000-0000-4000-8000-000000000003"
		)
		instance := h.newInstanceWithLifecycleKeys(
			t,
			[]byte("oauth-first-login-rls-receipt-key-000001"),
			"receipt-rls",
			nil,
			[]byte("oauth-first-login-rls-lookup-key-000001"),
			"lookup-rls",
			nil,
		)
		coordinator := newOAuthFirstLoginIntegrationCoordinator(
			t,
			instance,
			missingOrganizationID,
			missingProjectID,
		)
		command := oauthFirstLoginIntegrationCommand(
			h.now,
			missingOrganizationID,
			missingProjectID,
			"google",
			"google-integration-missing-scope-subject",
			"missing-scope@example.cn",
			"vault:oauth-first-login-missing-scope-token-ref",
			"Missing Scope",
		)
		before := snapshotOAuthFirstLoginDatabase(t, h.adminDB)
		result, receipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			command,
		)
		var oauthError OAuthError
		if !errors.As(err, &oauthError) ||
			oauthError.Status != http.StatusForbidden ||
			oauthError.Code != "oauth_first_login_not_authorized" ||
			oauthError.Cause != nil {
			t.Fatalf("unexpected missing-scope error: %#v", err)
		}
		if result != (OAuthFirstLoginCompletionResult{}) ||
			receipt.secret != nil {
			t.Fatalf(
				"missing scope returned a session handoff: result=%#v receipt=%#v",
				result,
				receipt,
			)
		}
		after := snapshotOAuthFirstLoginDatabase(t, h.adminDB)
		if !reflect.DeepEqual(before, after) {
			t.Fatalf(
				"missing trusted scope left mutations: before=%v after=%v",
				before,
				after,
			)
		}

		if _, err := instance.db.Exec(
			`SELECT count(*) FROM oauth_first_login_operations`,
		); err == nil {
			t.Fatal("runtime role directly selected the first-login operation ledger")
		}
		if _, err := instance.db.Exec(
			`INSERT INTO oauth_first_login_operations DEFAULT VALUES`,
		); err == nil {
			t.Fatal("runtime role directly inserted into the first-login operation ledger")
		}

		var runtimeSuperuser, runtimeBypassRLS bool
		if err := h.adminDB.QueryRow(`
SELECT rolsuper, rolbypassrls
  FROM pg_roles
 WHERE rolname=$1
`, h.runtimeRole).Scan(&runtimeSuperuser, &runtimeBypassRLS); err != nil {
			t.Fatalf("read disposable runtime role posture: %v", err)
		}
		if runtimeSuperuser || runtimeBypassRLS {
			t.Fatalf(
				"disposable runtime role bypasses isolation: superuser=%t bypassrls=%t",
				runtimeSuperuser,
				runtimeBypassRLS,
			)
		}

		const arrayAuthoritySignature = "public.a1_complete_oauth_first_login_with_refresh(uuid,uuid,text,text[],text[],text,text,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,jsonb)"
		var runtimeCanExecute, publicCanExecute, securityDefiner bool
		var ownerName string
		if err := h.adminDB.QueryRow(`
SELECT
  has_function_privilege($1, procedure.oid, 'EXECUTE'),
  EXISTS (
    SELECT 1
      FROM aclexplode(
        COALESCE(
          procedure.proacl,
          acldefault('f', procedure.proowner)
        )
      ) AS privilege
     WHERE privilege.grantee=0
       AND privilege.privilege_type='EXECUTE'
  ),
  procedure.prosecdef,
  pg_get_userbyid(procedure.proowner)
FROM pg_proc AS procedure
WHERE procedure.oid=to_regprocedure($2)
`, h.runtimeRole, arrayAuthoritySignature).Scan(
			&runtimeCanExecute,
			&publicCanExecute,
			&securityDefiner,
			&ownerName,
		); err != nil {
			t.Fatalf("read OAuth first-login authority ACL: %v", err)
		}
		if !runtimeCanExecute || publicCanExecute || !securityDefiner ||
			ownerName == h.runtimeRole {
			t.Fatalf(
				"unsafe OAuth authority ACL: runtime=%t public=%t security_definer=%t owner=%q",
				runtimeCanExecute,
				publicCanExecute,
				securityDefiner,
				ownerName,
			)
		}

		var rowSecurity, forceRowSecurity bool
		if err := h.adminDB.QueryRow(`
SELECT relrowsecurity, relforcerowsecurity
  FROM pg_class
 WHERE oid='public.oauth_first_login_operations'::regclass
`).Scan(&rowSecurity, &forceRowSecurity); err != nil {
			t.Fatalf("read OAuth first-login operation RLS posture: %v", err)
		}
		if !rowSecurity || !forceRowSecurity {
			t.Fatalf(
				"OAuth first-login operation RLS is not forced: enabled=%t forced=%t",
				rowSecurity,
				forceRowSecurity,
			)
		}
	})

	t.Run("lookup-key rotation upgrades one canonical GitHub identity", func(t *testing.T) {
		const (
			organizationID = "b4000000-0000-4000-8000-000000000001"
			workspaceID    = "b4000000-0000-4000-8000-000000000002"
			projectID      = "b4000000-0000-4000-8000-000000000003"
		)
		createIdentityVerificationProjectScope(
			t,
			h.adminDB,
			organizationID,
			workspaceID,
			projectID,
			"oauth-first-login-rotation",
		)
		lookupV1 := []byte("oauth-first-login-rotation-lookup-key-v1-001")
		lookupV2 := []byte("oauth-first-login-rotation-lookup-key-v2-001")
		oldInstance := h.newInstanceWithLifecycleKeys(
			t,
			[]byte("oauth-first-login-rotation-receipt-key-v1"),
			"receipt-rotation-v1",
			nil,
			lookupV1,
			"lookup-v1",
			nil,
		)
		oldCoordinator := newOAuthFirstLoginIntegrationCoordinator(
			t,
			oldInstance,
			organizationID,
			projectID,
		)
		firstCommand := oauthFirstLoginIntegrationCommand(
			h.now,
			organizationID,
			projectID,
			"github",
			"github-integration-lookup-rotation-subject",
			"lookup-rotation@example.cn",
			"vault:oauth-first-login-rotation-token-ref-v1",
			"Lookup Rotation",
		)
		oldSubjectDigest := firstPostgresOAuthFirstLoginDigest(
			oldCoordinator.store.lifecycleKeys.receiptDigests(
				strings.Join(
					[]string{
						"oauth-first-login",
						"provider-subject",
						firstCommand.Provider,
						firstCommand.ProviderSubject,
					},
					"\x00",
				),
			),
		)
		oldEmailDigest := firstPostgresOAuthFirstLoginDigest(
			oldCoordinator.store.lifecycleKeys.receiptDigests(
				strings.Join(
					[]string{
						"oauth-first-login",
						"verified-email",
						firstCommand.VerifiedEmail,
					},
					"\x00",
				),
			),
		)
		firstResult, firstReceipt, err :=
			oldCoordinator.CompleteOAuthFirstLogin(
				context.Background(),
				firstCommand,
			)
		if err != nil {
			t.Fatalf("complete pre-rotation GitHub first login: %v", err)
		}
		if !firstResult.Created || firstResult.Provider != "github" {
			t.Fatalf("unexpected pre-rotation result: %#v", firstResult)
		}
		firstAccessBearer, firstRefreshBearer, err :=
			firstReceipt.TakeBearerTokens()
		if err != nil {
			t.Fatalf("take pre-rotation GitHub bearer pair: %v", err)
		}
		if _, err := oldInstance.store.ResolveIdentityHTTPSession(
			context.Background(),
			oauthFirstLoginAccessRequest(firstAccessBearer),
		); err != nil {
			t.Fatalf("resolve pre-rotation GitHub session: %v", err)
		}

		newInstance := h.newInstanceWithLifecycleKeys(
			t,
			[]byte("oauth-first-login-rotation-receipt-key-v2"),
			"receipt-rotation-v2",
			nil,
			lookupV2,
			"lookup-v2",
			[]IdentityLifecycleLookupKey{
				{Version: "lookup-v1", Key: lookupV1},
			},
		)
		newCoordinator := newOAuthFirstLoginIntegrationCoordinator(
			t,
			newInstance,
			organizationID,
			projectID,
		)
		newSubjectDigest := firstPostgresOAuthFirstLoginDigest(
			newCoordinator.store.lifecycleKeys.receiptDigests(
				strings.Join(
					[]string{
						"oauth-first-login",
						"provider-subject",
						firstCommand.Provider,
						firstCommand.ProviderSubject,
					},
					"\x00",
				),
			),
		)
		newEmailDigest := firstPostgresOAuthFirstLoginDigest(
			newCoordinator.store.lifecycleKeys.receiptDigests(
				strings.Join(
					[]string{
						"oauth-first-login",
						"verified-email",
						firstCommand.VerifiedEmail,
					},
					"\x00",
				),
			),
		)
		if oldSubjectDigest == "" || oldEmailDigest == "" ||
			newSubjectDigest == "" || newEmailDigest == "" ||
			oldSubjectDigest == newSubjectDigest ||
			oldEmailDigest == newEmailDigest {
			t.Fatal("lookup-key rotation did not produce distinct active digests")
		}

		secondCommand := firstCommand
		secondCommand.TokenRef = "vault:oauth-first-login-rotation-token-ref-v2"
		secondResult, secondReceipt, err :=
			newCoordinator.CompleteOAuthFirstLogin(
				context.Background(),
				secondCommand,
			)
		if err != nil {
			t.Fatalf("complete post-rotation GitHub first login: %v", err)
		}
		if secondResult.Created ||
			secondResult.AccountID != firstResult.AccountID ||
			secondResult.CredentialID != firstResult.CredentialID ||
			secondResult.SessionID == firstResult.SessionID ||
			secondResult.Provider != "github" {
			t.Fatalf(
				"lookup-key rotation split canonical identity: first=%#v second=%#v",
				firstResult,
				secondResult,
			)
		}
		secondAccessBearer, secondRefreshBearer, err :=
			secondReceipt.TakeBearerTokens()
		if err != nil {
			t.Fatalf("take post-rotation GitHub bearer pair: %v", err)
		}
		if _, err := newInstance.store.ResolveIdentityHTTPSession(
			context.Background(),
			oauthFirstLoginAccessRequest(secondAccessBearer),
		); err != nil {
			t.Fatalf("resolve post-rotation GitHub session: %v", err)
		}

		var credentialDigest, accountEmailDigest string
		if err := h.adminDB.QueryRow(`
SELECT credential.subject_digest, account_email.normalized_email_digest
  FROM identity_credentials AS credential
  JOIN identity_account_emails AS account_email
    ON account_email.principal_id=credential.principal_id
 WHERE credential.id=$1::uuid
`, secondResult.CredentialID).Scan(
			&credentialDigest,
			&accountEmailDigest,
		); err != nil {
			t.Fatalf("read rotated canonical credential/email digests: %v", err)
		}
		if credentialDigest != newSubjectDigest ||
			accountEmailDigest != newEmailDigest {
			t.Fatalf(
				"canonical credential/email digests were not upgraded: subject=%t email=%t",
				credentialDigest == newSubjectDigest,
				accountEmailDigest == newEmailDigest,
			)
		}

		var connectionAccountID, connectionSubjectDigest string
		var connectionEmailDigest sql.NullString
		if err := h.adminDB.QueryRow(`
SELECT account_id, provider_subject_digest, email_digest
  FROM oauth_account_connections
 WHERE organization_id=$1::uuid
   AND project_id=$2::uuid
   AND principal_id=$3::uuid
   AND credential_id=$4::uuid
   AND provider='github'
`, organizationID, projectID, secondResult.AccountID, secondResult.CredentialID).Scan(
			&connectionAccountID,
			&connectionSubjectDigest,
			&connectionEmailDigest,
		); err != nil {
			t.Fatalf("read rotated OAuth connection digests: %v", err)
		}
		if connectionAccountID != newSubjectDigest ||
			connectionSubjectDigest != newSubjectDigest ||
			!connectionEmailDigest.Valid ||
			connectionEmailDigest.String != newEmailDigest {
			t.Fatal("OAuth connection retained a retired lookup digest")
		}
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT
			   (SELECT count(*) FROM identity_credentials
			     WHERE subject_digest=$1)
			 + (SELECT count(*) FROM identity_account_emails
			     WHERE normalized_email_digest=$2)
			 + (SELECT count(*) FROM oauth_account_connections
			     WHERE account_id=$1
			        OR provider_subject_digest=$1
			        OR email_digest=$2)`,
			0,
			oldSubjectDigest,
			oldEmailDigest,
		)

		var sessionKeyVersion, lookupKeyVersion string
		if err := h.adminDB.QueryRow(`
SELECT metadata->>'session_key_version',
       metadata->>'identity_lookup_key_version'
  FROM identity_sessions
 WHERE id=$1::uuid
`, secondResult.SessionID).Scan(
			&sessionKeyVersion,
			&lookupKeyVersion,
		); err != nil {
			t.Fatalf("read post-rotation session key metadata: %v", err)
		}
		if sessionKeyVersion != "integration" ||
			lookupKeyVersion != "lookup-v2" ||
			secondReceipt.keyVersion != sessionKeyVersion ||
			secondReceipt.refreshKeyVersion != sessionKeyVersion {
			t.Fatalf(
				"unexpected post-rotation key versions: session=%q lookup=%q receipt=%q/%q",
				sessionKeyVersion,
				lookupKeyVersion,
				secondReceipt.keyVersion,
				secondReceipt.refreshKeyVersion,
			)
		}
		assertOAuthFirstLoginOpaqueReferenceStatus(
			t,
			h.adminDB,
			firstCommand.TokenRef,
			"revocation_pending",
		)
		assertOAuthFirstLoginOpaqueReferenceStatus(
			t,
			h.adminDB,
			secondCommand.TokenRef,
			"active",
		)
		assertOAuthFirstLoginDatabaseCount(
			t,
			h.adminDB,
			`SELECT count(*) FROM oauth_revocation_outbox AS outbox
			  JOIN oauth_token_opaque_refs AS token_ref
			    ON token_ref.organization_id=outbox.organization_id
			   AND token_ref.project_id=outbox.project_id
			   AND token_ref.id=outbox.token_ref_id
			 WHERE token_ref.opaque_ref=$1
			   AND outbox.reason_code='first_login_reauthenticated'
			   AND outbox.status='pending'`,
			1,
			firstCommand.TokenRef,
		)
		assertOAuthFirstLoginNoRawMaterial(
			t,
			h.adminDB,
			[]oauthFirstLoginForbiddenMaterial{
				{label: "rotated provider subject", value: firstCommand.ProviderSubject},
				{label: "rotated verified email", value: firstCommand.VerifiedEmail},
				{label: "pre-rotation access bearer", value: firstAccessBearer},
				{label: "pre-rotation refresh bearer", value: firstRefreshBearer},
				{label: "post-rotation access bearer", value: secondAccessBearer},
				{label: "post-rotation refresh bearer", value: secondRefreshBearer},
			},
		)

		firstAccessBearer = ""
		firstRefreshBearer = ""
		secondAccessBearer = ""
		secondRefreshBearer = ""
	})
}

func newOAuthFirstLoginIntegrationCoordinator(
	t *testing.T,
	instance *postgresLifecycleInstance,
	organizationID string,
	projectID string,
) *PostgresOAuthFirstLoginCoordinator {
	t.Helper()
	coordinator, err := NewPostgresOAuthFirstLoginCoordinator(
		PostgresOAuthFirstLoginCoordinatorOptions{
			Store:          instance.store,
			OrganizationID: organizationID,
			ProjectID:      projectID,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	return coordinator
}

func oauthFirstLoginIntegrationCommand(
	now time.Time,
	organizationID string,
	projectID string,
	provider string,
	subject string,
	email string,
	tokenRef string,
	displayName string,
) OAuthFirstLoginCompletionCommand {
	return OAuthFirstLoginCompletionCommand{
		SchemaVersion:   OAuthFirstLoginSchemaVersion,
		Purpose:         OAuthPurposeFirstLogin,
		OrganizationID:  organizationID,
		ProjectID:       projectID,
		Provider:        provider,
		ProviderSubject: subject,
		DisplayName:     displayName,
		VerifiedEmail:   email,
		TokenRef:        tokenRef,
		CompletedAt:     now.UTC(),
	}
}

func oauthFirstLoginAccessRequest(bearer string) *http.Request {
	request := httptest.NewRequest(
		http.MethodGet,
		"https://api.example.test/v1/identity/account",
		nil,
	)
	request.Header.Set("Authorization", "Bearer "+bearer)
	return request
}

func snapshotOAuthFirstLoginDatabase(
	t *testing.T,
	db *sql.DB,
) oauthFirstLoginDatabaseSnapshot {
	t.Helper()
	snapshot := make(oauthFirstLoginDatabaseSnapshot)
	for _, table := range oauthFirstLoginPersistenceTables() {
		var count int64
		if err := db.QueryRow(
			`SELECT count(*) FROM ` + quotePostgresIdentifier(table),
		).Scan(&count); err != nil {
			t.Fatalf("snapshot %s: %v", table, err)
		}
		snapshot[table] = count
	}
	return snapshot
}

func assertOAuthFirstLoginSnapshotDelta(
	t *testing.T,
	before oauthFirstLoginDatabaseSnapshot,
	after oauthFirstLoginDatabaseSnapshot,
	expected map[string]int64,
) {
	t.Helper()
	for _, table := range oauthFirstLoginPersistenceTables() {
		want, ok := expected[table]
		if !ok {
			t.Fatalf("missing expected snapshot delta for %s", table)
		}
		if got := after[table] - before[table]; got != want {
			t.Fatalf(
				"unexpected %s delta: got=%d want=%d before=%d after=%d",
				table,
				got,
				want,
				before[table],
				after[table],
			)
		}
	}
}

func assertOAuthFirstLoginDatabaseCount(
	t *testing.T,
	db *sql.DB,
	query string,
	want int64,
	arguments ...any,
) {
	t.Helper()
	var got int64
	if err := db.QueryRow(query, arguments...).Scan(&got); err != nil {
		t.Fatalf("read OAuth first-login database count: %v", err)
	}
	if got != want {
		t.Fatalf("unexpected OAuth first-login database count: got=%d want=%d", got, want)
	}
}

func assertOAuthFirstLoginOpaqueReferenceStatus(
	t *testing.T,
	db *sql.DB,
	opaqueReference string,
	want string,
) {
	t.Helper()
	var got string
	if err := db.QueryRow(
		`SELECT status FROM oauth_token_opaque_refs WHERE opaque_ref=$1`,
		opaqueReference,
	).Scan(&got); err != nil {
		t.Fatalf("read OAuth opaque-reference status: %v", err)
	}
	if got != want {
		t.Fatalf("unexpected OAuth opaque-reference status: got=%q want=%q", got, want)
	}
}

func assertOAuthFirstLoginNoRawMaterial(
	t *testing.T,
	db *sql.DB,
	forbidden []oauthFirstLoginForbiddenMaterial,
) {
	t.Helper()
	for _, table := range oauthFirstLoginPersistenceTables() {
		var projection string
		query := `SELECT COALESCE(
  jsonb_agg(to_jsonb(persisted)),
  '[]'::jsonb
)::text
FROM ` + quotePostgresIdentifier(table) + ` AS persisted`
		if err := db.QueryRow(query).Scan(&projection); err != nil {
			t.Fatalf("project %s for secret audit: %v", table, err)
		}
		for _, material := range forbidden {
			if material.value != "" &&
				strings.Contains(projection, material.value) {
				t.Fatalf(
					"%s persisted forbidden %s material",
					table,
					material.label,
				)
			}
		}
	}
}

func oauthFirstLoginPersistenceTables() []string {
	return []string{
		"identity_principals",
		"identity_credentials",
		"identity_organization_memberships",
		"identity_project_memberships",
		"identity_account_emails",
		"identity_account_security",
		"identity_sessions",
		"identity_session_lifecycle_operations",
		"oauth_token_opaque_refs",
		"oauth_account_connections",
		"oauth_revocation_outbox",
		"oauth_first_login_operations",
		"identity_audit_events",
	}
}
