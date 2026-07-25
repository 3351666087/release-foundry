package ashrclone

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	_ "github.com/lib/pq"
)

const identityLifecyclePostgresIntegrationFlag = "ASHR_RUN_IDENTITY_LIFECYCLE_POSTGRES_INTEGRATION"

type postgresLifecycleHarness struct {
	adminDSN    string
	dbName      string
	adminDB     *sql.DB
	runtimeDSN  string
	runtimeRole string
	issuerDSN   string
	issuerRole  string
	now         time.Time
}

type postgresLifecycleInstance struct {
	db                    *sql.DB
	adminDB               *sql.DB
	store                 *ProductionIdentityStore
	receipts              *postgresIdentityLifecycleReceiptStore
	service               *IdentityLifecycleService
	credentialLinkService *IdentityCredentialLinkService
}

func TestIdentityLifecyclePostgresIntegration(t *testing.T) {
	if os.Getenv(identityLifecyclePostgresIntegrationFlag) != "1" {
		t.Skip("set " + identityLifecyclePostgresIntegrationFlag + "=1 to run PostgreSQL identity lifecycle integration tests")
	}
	adminDSN := strings.TrimSpace(os.Getenv("ASHR_IDENTITY_LIFECYCLE_TEST_DSN"))
	if adminDSN == "" {
		t.Skip("ASHR_IDENTITY_LIFECYCLE_TEST_DSN is not configured")
	}

	t.Run("atomic registration, replay, separation and rollback", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		first := h.newInstance(t, []byte("lifecycle-key-v1-0123456789012345"), "v1", nil)
		second := h.newInstance(t, []byte("lifecycle-key-v1-0123456789012345"), "v1", nil)

		receipt := issueLifecycleProof(t, first.service, TrustedIdentityProof{
			Operation:     IdentityOperationRegistration,
			Kind:          IdentityCredentialEmail,
			Provider:      IdentityProviderLocal,
			Identifier:    "atomic-owner@example.cn",
			VerifiedEmail: "atomic-owner@example.cn",
			DisplayName:   "Atomic Owner",
		})
		var successes atomic.Int32
		var consumed atomic.Int32
		var wait sync.WaitGroup
		for index := 0; index < 24; index++ {
			wait.Add(1)
			go func(index int) {
				defer wait.Done()
				service := first.service
				if index%2 == 1 {
					service = second.service
				}
				_, err := service.CompleteRegistration(completionFor(receipt))
				switch {
				case err == nil:
					successes.Add(1)
				case errors.Is(err, ErrIdentityProofReceiptConsumed):
					consumed.Add(1)
				default:
					t.Errorf("concurrent completion returned %v", err)
				}
			}(index)
		}
		wait.Wait()
		if successes.Load() != 1 || consumed.Load() != 23 {
			t.Fatalf("receipt completion was not exactly-once: success=%d consumed=%d", successes.Load(), consumed.Load())
		}
		assertIdentityCounts(t, first.adminDB, 1, 1)

		unknown := issueLifecycleProof(t, second.service, TrustedIdentityProof{
			Operation: IdentityOperationLogin, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "unknown@example.cn",
		})
		if _, err := second.service.CompleteLogin(completionFor(unknown)); !errors.Is(err, ErrIdentityCredentialNotFound) {
			t.Fatalf("unknown login returned %v", err)
		}
		assertIdentityCounts(t, first.adminDB, 1, 1)
		if _, err := second.service.CompleteLogin(completionFor(unknown)); !errors.Is(err, ErrIdentityCredentialNotFound) {
			t.Fatalf("failed login receipt was not retryable: %v", err)
		}

		duplicate := issueLifecycleProof(t, second.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "atomic-owner@example.cn",
		})
		var domain IdentityDomainError
		if _, err := second.service.CompleteRegistration(completionFor(duplicate)); !errors.As(err, &domain) ||
			domain.Code != "credential_already_registered" {
			t.Fatalf("duplicate registration returned %v", err)
		}
		assertIdentityCounts(t, first.adminDB, 1, 1)

		scoped := issueLifecycleProof(t, first.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "scoped@example.cn",
			TenantID: "tenant-a", ProjectID: "project-a",
		})
		mismatch := completionFor(scoped)
		mismatch.TenantID = "tenant-b"
		if _, err := second.service.CompleteRegistration(mismatch); !errors.Is(err, ErrIdentityProofScopeMismatch) {
			t.Fatalf("scope mismatch returned %v", err)
		}
		if _, err := second.service.CompleteRegistration(completionFor(scoped)); err != nil {
			t.Fatalf("scope mismatch consumed receipt: %v", err)
		}

		rollback := issueLifecycleProof(t, first.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "rollback@example.cn",
		})
		mustExec(t, first.adminDB, `
CREATE OR REPLACE FUNCTION reject_identity_session_for_test() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected session failure'; END $$;
CREATE TRIGGER reject_identity_session_for_test
BEFORE INSERT ON identity_sessions FOR EACH ROW EXECUTE FUNCTION reject_identity_session_for_test();
`)
		if _, err := first.service.CompleteRegistration(completionFor(rollback)); err == nil ||
			!strings.Contains(err.Error(), "injected session failure") {
			t.Fatalf("rollback injection returned %v", err)
		}
		mustExec(t, first.adminDB, `
DROP TRIGGER reject_identity_session_for_test ON identity_sessions;
DROP FUNCTION reject_identity_session_for_test();
`)
		if _, err := second.service.CompleteRegistration(completionFor(rollback)); err != nil {
			t.Fatalf("rolled-back receipt was not retryable: %v", err)
		}
	})

	t.Run("verified email registration and accountless login session handoff", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		instance := h.newInstance(
			t,
			[]byte("verification-lifecycle-key-012345678901"),
			"v1",
			nil,
		)

		organizationID := "90000000-0000-4000-8000-000000000001"
		workspaceID := "90000000-0000-4000-8000-000000000002"
		projectID := "90000000-0000-4000-8000-000000000003"
		otherProjectID := "90000000-0000-4000-8000-000000000004"
		createIdentityVerificationProjectScope(
			t,
			instance.adminDB,
			organizationID,
			workspaceID,
			projectID,
			"verification-primary",
		)
		mustExecArgs(t, instance.adminDB, `
INSERT INTO projects(id,organization_id,workspace_id,slug,display_name)
VALUES ($1::uuid,$2::uuid,$3::uuid,'verification-secondary','Verification Secondary')
`, otherProjectID, organizationID, workspaceID)

		foreignOrganizationID := "a0000000-0000-4000-8000-000000000001"
		foreignWorkspaceID := "a0000000-0000-4000-8000-000000000002"
		foreignProjectID := "a0000000-0000-4000-8000-000000000003"
		createIdentityVerificationProjectScope(
			t,
			instance.adminDB,
			foreignOrganizationID,
			foreignWorkspaceID,
			foreignProjectID,
			"verification-foreign",
		)

		verificationDigestKey := []byte(
			"verification-integration-digest-key-0123456789",
		)
		newVerificationService := func(
			organizationID string,
			projectID string,
			sealRef string,
		) (*IdentityVerificationService, *PostgresIdentityVerificationStore, *recordingIdentityDeliveryVault) {
			t.Helper()
			verificationStore, err := instance.store.NewIdentityVerificationStore(
				PostgresIdentityVerificationStoreOptions{
					OrganizationID:   organizationID,
					ProjectID:        projectID,
					DigestKey:        verificationDigestKey,
					OperationTimeout: 10 * time.Second,
				},
			)
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(verificationStore.Close)
			coordinator, err := instance.store.NewIdentityVerificationTransactionCoordinator(
				verificationStore,
			)
			if err != nil {
				t.Fatal(err)
			}
			vault := &recordingIdentityDeliveryVault{sealRef: sealRef}
			service, err := NewIdentityVerificationService(
				IdentityVerificationServiceOptions{
					Store:                  verificationStore,
					DeliveryVaultSealer:    vault,
					DeliveryVaultDeleter:   vault,
					TransactionCoordinator: coordinator,
					Now:                    func() time.Time { return h.now },
					DigestKey:              verificationDigestKey,
					TTL:                    5 * time.Minute,
					AttemptCap:             3,
					ResendCooldown:         time.Second,
				},
			)
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(service.Close)
			return service, verificationStore, vault
		}

		registrationService, registrationStore, registrationVault := newVerificationService(
			organizationID,
			projectID,
			"vault:identity-delivery/registration-live",
		)
		registrationIdentifier := "registration-live@example.cn"
		registrationChallenge, err := registrationService.Start(
			context.Background(),
			IdentityVerificationStartRequest{
				Channel:    IdentityVerificationEmail,
				Identifier: registrationIdentifier,
				Purpose:    IdentityVerificationRegistration,
				TenantID:   organizationID,
			},
		)
		if err != nil {
			t.Fatalf("start verified registration: %v", err)
		}
		if registrationChallenge.ChallengeID == "" ||
			registrationChallenge.AccountBound ||
			registrationVault.sealRequest.ChallengeHandle !=
				registrationChallenge.ChallengeID ||
			registrationVault.sealRequest.Code == "" {
			t.Fatal("registration did not produce a private delivery and public accountless challenge handle")
		}
		registrationCompletion := IdentityVerificationCompleteRequest{
			ChallengeID: registrationChallenge.ChallengeID,
			Code:        registrationVault.sealRequest.Code,
			Channel:     IdentityVerificationEmail,
			Identifier:  registrationIdentifier,
			Purpose:     IdentityVerificationRegistration,
			TenantID:    organizationID,
			DisplayName: "Verified Registration",
		}
		if _, err := registrationService.Complete(
			context.Background(),
			registrationCompletion,
		); verificationErrorCode(err) != "session_issuance_required" {
			t.Fatalf("public registration completion bypassed trusted session issuance: %v", err)
		}
		registrationResult, registrationIssuance, err :=
			registrationService.CompleteAndIssueSession(
				context.Background(),
				registrationCompletion,
			)
		if err != nil {
			t.Fatalf("complete verified registration: %v", err)
		}
		if registrationResult.Account.AccountID == "" ||
			registrationResult.Credential.CredentialID == "" ||
			!registrationResult.Created ||
			registrationResult.Account.AccountID ==
				registrationResult.Credential.CredentialID ||
			registrationIssuance.SessionID() == "" {
			t.Fatalf(
				"verified registration did not return canonical identifiers: result=%#v receipt=%v",
				registrationResult,
				registrationIssuance,
			)
		}
		accessBearer, refreshBearer, err := registrationIssuance.TakeBearerTokens()
		if err != nil || accessBearer == "" || refreshBearer == "" ||
			accessBearer == refreshBearer {
			t.Fatalf(
				"verified registration did not hand off a distinct bearer pair: access_nonempty=%t refresh_nonempty=%t distinct=%t err=%v",
				accessBearer != "",
				refreshBearer != "",
				accessBearer != refreshBearer,
				err,
			)
		}
		accessDigest, _, err := instance.store.sessionTokens.digest(accessBearer)
		if err != nil {
			t.Fatal("issued access bearer could not be digested")
		}
		refreshDigest, _, err := instance.store.sessionTokens.digestRefresh(
			refreshBearer,
		)
		if err != nil {
			t.Fatal("issued refresh bearer could not be digested")
		}
		identifierDigest := registrationService.digest(
			"identifier",
			string(IdentityCredentialEmail),
			registrationIdentifier,
		)
		challengeDigest := registrationStore.challengeDigest(
			registrationChallenge.ChallengeID,
		)
		var (
			principalValid              bool
			credentialValid             bool
			canonicalEmailValid         bool
			securityPostureValid        bool
			organizationMembershipValid bool
			projectMembershipValid      bool
			sessionValid                bool
			receiptValid                bool
			auditValid                  bool
		)
		if err := instance.adminDB.QueryRow(`
SELECT
  EXISTS (
    SELECT 1 FROM identity_principals
     WHERE id=$1::uuid AND status='active' AND display_label=$2
  ),
  EXISTS (
    SELECT 1 FROM identity_credentials
     WHERE id=$3::uuid AND principal_id=$1::uuid
       AND provider='email' AND credential_kind='email_otp'
       AND subject_digest=$4 AND status='active' AND login_enabled
       AND verified_at IS NOT NULL
  ),
  EXISTS (
    SELECT 1 FROM identity_account_emails
     WHERE principal_id=$1::uuid AND normalized_email_digest=$4
       AND source_provider='email' AND verified_at IS NOT NULL
  ),
  EXISTS (
    SELECT 1 FROM identity_account_security
     WHERE principal_id=$1::uuid AND two_factor_status='disabled'
       AND two_factor_recommended AND two_factor_enrolled_at IS NULL
  ),
  EXISTS (
    SELECT 1 FROM identity_organization_memberships
     WHERE organization_id=$5::uuid AND principal_id=$1::uuid
       AND role='member' AND status='active' AND activated_at IS NOT NULL
  ),
  EXISTS (
    SELECT 1 FROM identity_project_memberships
     WHERE organization_id=$5::uuid AND project_id=$6::uuid
       AND principal_id=$1::uuid AND role='member' AND status='active'
       AND activated_at IS NOT NULL
  ),
  EXISTS (
    SELECT 1 FROM identity_sessions
     WHERE id=$7::uuid AND principal_id=$1::uuid AND credential_id=$3::uuid
       AND organization_id=$5::uuid AND project_id=$6::uuid
       AND session_digest=$8 AND refresh_digest=$9
       AND status='active' AND assurance_level='aal1'
       AND refresh_expires_at > expires_at
  ),
  EXISTS (
    SELECT 1
      FROM identity_verification_receipts AS receipt
      JOIN identity_verification_challenges AS challenge
        ON challenge.id=receipt.challenge_id
     WHERE challenge.challenge_digest=$10
       AND receipt.status='consumed'
       AND receipt.purpose='registration'
       AND receipt.principal_id IS NULL
       AND receipt.mutation_kind='registration'
       AND receipt.mutation_result_id=$7::uuid
       AND receipt.consumed_at IS NOT NULL
  ),
  EXISTS (
    SELECT 1
      FROM identity_verification_audit_events AS event
      JOIN identity_verification_challenges AS challenge
        ON challenge.id=event.challenge_id
     WHERE challenge.challenge_digest=$10
       AND event.principal_id=$1::uuid
       AND event.event_type='registration_succeeded'
       AND event.outcome_code='registered'
  )
`,
			registrationResult.Account.AccountID,
			registrationCompletion.DisplayName,
			registrationResult.Credential.CredentialID,
			identifierDigest,
			organizationID,
			projectID,
			registrationIssuance.SessionID(),
			accessDigest,
			refreshDigest,
			challengeDigest,
		).Scan(
			&principalValid,
			&credentialValid,
			&canonicalEmailValid,
			&securityPostureValid,
			&organizationMembershipValid,
			&projectMembershipValid,
			&sessionValid,
			&receiptValid,
			&auditValid,
		); err != nil {
			t.Fatal(err)
		}
		if !principalValid || !credentialValid || !canonicalEmailValid ||
			!securityPostureValid || !organizationMembershipValid ||
			!projectMembershipValid || !sessionValid || !receiptValid ||
			!auditValid {
			t.Fatalf(
				"verified registration projection principal=%t credential=%t email=%t security=%t organization_membership=%t project_membership=%t session=%t receipt=%t audit=%t",
				principalValid,
				credentialValid,
				canonicalEmailValid,
				securityPostureValid,
				organizationMembershipValid,
				projectMembershipValid,
				sessionValid,
				receiptValid,
				auditValid,
			)
		}

		httpRequest, err := http.NewRequest(
			http.MethodGet,
			"https://api.example.test/v1/identity/session",
			nil,
		)
		if err != nil {
			t.Fatal(err)
		}
		httpRequest.Header.Set("Authorization", "Bearer "+accessBearer)
		resolved, err := instance.store.ResolveIdentityHTTPSession(
			context.Background(),
			httpRequest,
		)
		if err != nil ||
			resolved.AccountID != registrationResult.Account.AccountID ||
			resolved.SessionID != registrationIssuance.SessionID() {
			t.Fatalf("issued registration session did not resolve canonically: session=%#v err=%v", resolved, err)
		}
		refreshRequest, err := http.NewRequest(
			http.MethodGet,
			"https://api.example.test/v1/identity/session",
			nil,
		)
		if err != nil {
			t.Fatal(err)
		}
		refreshRequest.Header.Set("Authorization", "Bearer "+refreshBearer)
		if _, err := instance.store.ResolveIdentityHTTPSession(
			context.Background(),
			refreshRequest,
		); err == nil {
			t.Fatal("refresh bearer authenticated as an access session")
		}

		loginService, _, loginVault := newVerificationService(
			organizationID,
			projectID,
			"vault:identity-delivery/login-live",
		)
		loginChallenge, err := loginService.Start(
			context.Background(),
			IdentityVerificationStartRequest{
				Channel:    IdentityVerificationEmail,
				Identifier: registrationIdentifier,
				Purpose:    IdentityVerificationLogin,
				TenantID:   organizationID,
			},
		)
		if err != nil {
			t.Fatalf("start accountless login: %v", err)
		}
		loginResult, loginIssuance, err := loginService.CompleteAndIssueSession(
			context.Background(),
			IdentityVerificationCompleteRequest{
				ChallengeID: loginChallenge.ChallengeID,
				Code:        loginVault.sealRequest.Code,
				Channel:     IdentityVerificationEmail,
				Identifier:  registrationIdentifier,
				Purpose:     IdentityVerificationLogin,
				TenantID:    organizationID,
			},
		)
		if err != nil {
			t.Fatalf("complete accountless login: %v", err)
		}
		if loginResult.Account.AccountID != registrationResult.Account.AccountID ||
			loginResult.Credential.CredentialID !=
				registrationResult.Credential.CredentialID ||
			loginResult.Created ||
			loginIssuance.SessionID() == "" ||
			loginIssuance.SessionID() == registrationIssuance.SessionID() {
			t.Fatalf(
				"accountless login did not reuse the canonical account and credential: result=%#v receipt=%v",
				loginResult,
				loginIssuance,
			)
		}
		loginAccessBearer, loginRefreshBearer, err :=
			loginIssuance.TakeBearerTokens()
		if err != nil || loginAccessBearer == "" || loginRefreshBearer == "" {
			t.Fatalf(
				"accountless login bearer handoff failed: access_nonempty=%t refresh_nonempty=%t err=%v",
				loginAccessBearer != "",
				loginRefreshBearer != "",
				err,
			)
		}
		loginRequest, err := http.NewRequest(
			http.MethodGet,
			"https://api.example.test/v1/identity/session",
			nil,
		)
		if err != nil {
			t.Fatal(err)
		}
		loginRequest.Header.Set("Authorization", "Bearer "+loginAccessBearer)
		loginSession, err := instance.store.ResolveIdentityHTTPSession(
			context.Background(),
			loginRequest,
		)
		if err != nil ||
			loginSession.AccountID != registrationResult.Account.AccountID ||
			loginSession.SessionID != loginIssuance.SessionID() {
			t.Fatalf("accountless login session did not resolve canonically: session=%#v err=%v", loginSession, err)
		}

		time.Sleep(1100 * time.Millisecond)
		duplicateService, duplicateStore, duplicateVault := newVerificationService(
			organizationID,
			projectID,
			"vault:identity-delivery/registration-duplicate",
		)
		duplicateChallenge, err := duplicateService.Start(
			context.Background(),
			IdentityVerificationStartRequest{
				Channel:    IdentityVerificationEmail,
				Identifier: registrationIdentifier,
				Purpose:    IdentityVerificationRegistration,
				TenantID:   organizationID,
			},
		)
		if err != nil {
			t.Fatalf("start duplicate registration: %v", err)
		}
		if _, _, err := duplicateService.CompleteAndIssueSession(
			context.Background(),
			IdentityVerificationCompleteRequest{
				ChallengeID: duplicateChallenge.ChallengeID,
				Code:        duplicateVault.sealRequest.Code,
				Channel:     IdentityVerificationEmail,
				Identifier:  registrationIdentifier,
				Purpose:     IdentityVerificationRegistration,
				TenantID:    organizationID,
				DisplayName: "Duplicate Registration",
			},
		); verificationErrorCode(err) != "verification_mutation_rejected" {
			t.Fatalf("duplicate registration was not rejected atomically: %v", err)
		}
		duplicateChallengeDigest := duplicateStore.challengeDigest(
			duplicateChallenge.ChallengeID,
		)
		var (
			principalCount        int
			credentialCount       int
			sessionCount          int
			duplicateStatus       string
			duplicateAttemptCount int
			duplicateReceiptCount int
		)
		if err := instance.adminDB.QueryRow(`
SELECT
  (SELECT count(*) FROM identity_principals),
  (SELECT count(*) FROM identity_credentials),
  (SELECT count(*) FROM identity_sessions),
  challenge.status,
  challenge.attempt_count,
  (
    SELECT count(*) FROM identity_verification_receipts AS receipt
     WHERE receipt.challenge_id=challenge.id
  )
  FROM identity_verification_challenges AS challenge
 WHERE challenge.challenge_digest=$1
`, duplicateChallengeDigest).Scan(
			&principalCount,
			&credentialCount,
			&sessionCount,
			&duplicateStatus,
			&duplicateAttemptCount,
			&duplicateReceiptCount,
		); err != nil {
			t.Fatal(err)
		}
		if principalCount != 1 || credentialCount != 1 || sessionCount != 2 ||
			duplicateStatus != "pending" || duplicateAttemptCount != 0 ||
			duplicateReceiptCount != 0 {
			t.Fatalf(
				"duplicate registration rollback principals=%d credentials=%d sessions=%d status=%q attempts=%d receipts=%d",
				principalCount,
				credentialCount,
				sessionCount,
				duplicateStatus,
				duplicateAttemptCount,
				duplicateReceiptCount,
			)
		}

		scopeService, scopeStore, scopeVault := newVerificationService(
			organizationID,
			projectID,
			"vault:identity-delivery/scope-live",
		)
		scopeIdentifier := "registration-scope@example.cn"
		scopeChallenge, err := scopeService.Start(
			context.Background(),
			IdentityVerificationStartRequest{
				Channel:    IdentityVerificationEmail,
				Identifier: scopeIdentifier,
				Purpose:    IdentityVerificationRegistration,
				TenantID:   organizationID,
			},
		)
		if err != nil {
			t.Fatalf("start scoped registration: %v", err)
		}
		for _, mismatch := range []struct {
			name           string
			organizationID string
			projectID      string
			sealRef        string
		}{
			{
				name:           "project",
				organizationID: organizationID,
				projectID:      otherProjectID,
				sealRef:        "vault:identity-delivery/scope-project",
			},
			{
				name:           "organization",
				organizationID: foreignOrganizationID,
				projectID:      foreignProjectID,
				sealRef:        "vault:identity-delivery/scope-organization",
			},
		} {
			t.Run("reject mismatched "+mismatch.name, func(t *testing.T) {
				mismatchService, _, _ := newVerificationService(
					mismatch.organizationID,
					mismatch.projectID,
					mismatch.sealRef,
				)
				if _, _, err := mismatchService.CompleteAndIssueSession(
					context.Background(),
					IdentityVerificationCompleteRequest{
						ChallengeID: scopeChallenge.ChallengeID,
						Code:        scopeVault.sealRequest.Code,
						Channel:     IdentityVerificationEmail,
						Identifier:  scopeIdentifier,
						Purpose:     IdentityVerificationRegistration,
						TenantID:    mismatch.organizationID,
						DisplayName: "Scope Rejection",
					},
				); verificationErrorCode(err) != "verification_rejected" {
					t.Fatalf("mismatched %s scope returned %v", mismatch.name, err)
				}
			})
		}
		scopeChallengeDigest := scopeStore.challengeDigest(scopeChallenge.ChallengeID)
		var scopeStatus string
		var scopeAttempts, scopeReceipts int
		if err := instance.adminDB.QueryRow(`
SELECT challenge.status, challenge.attempt_count,
       (
         SELECT count(*) FROM identity_verification_receipts AS receipt
          WHERE receipt.challenge_id=challenge.id
       )
  FROM identity_verification_challenges AS challenge
 WHERE challenge.challenge_digest=$1
`, scopeChallengeDigest).Scan(
			&scopeStatus,
			&scopeAttempts,
			&scopeReceipts,
		); err != nil {
			t.Fatal(err)
		}
		if scopeStatus != "pending" || scopeAttempts != 0 || scopeReceipts != 0 {
			t.Fatalf(
				"scope mismatch mutated original challenge status=%q attempts=%d receipts=%d",
				scopeStatus,
				scopeAttempts,
				scopeReceipts,
			)
		}

		for _, table := range []string{
			"identity_verification_cooldowns",
			"identity_verification_challenges",
			"identity_verification_receipts",
			"identity_verification_delivery_outbox",
			"identity_verification_abuse_buckets",
			"identity_verification_audit_events",
		} {
			var count int
			if err := instance.db.QueryRow(
				"SELECT count(*) FROM " + table,
			).Scan(&count); err == nil {
				t.Fatalf("runtime role read protected verification table %s", table)
			}
		}
	})

	t.Run("projection, exact login credential and public serialization", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		instance := h.newInstance(t, []byte("projection-key-v1-012345678901234"), "v1", nil)
		registration := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialOAuth,
			Provider: IdentityProviderGoogle, Identifier: "google-owner-subject",
			VerifiedEmail: "owner@example.com", DisplayName: "Projection Owner",
		})
		account, err := instance.service.CompleteRegistration(completionFor(registration))
		if err != nil {
			t.Fatal(err)
		}
		if account.SecurityPosture.Password.Status != "absent" {
			t.Fatalf("OAuth-first account unexpectedly has a password: %#v", account.SecurityPosture.Password)
		}

		emailDigest := instance.receipts.receiptDigest("credential:" + string(IdentityProviderLocal) + ":owner@example.cn")
		var emailCredentialID string
		err = instance.adminDB.QueryRow(`
INSERT INTO identity_credentials(
  principal_id,provider,provider_environment,credential_kind,subject_digest,
  status,login_enabled,verified_at,last_authenticated_at,metadata
) VALUES (
  $1::uuid,'email','production','email_otp',$2,
  'active',TRUE,$3,$3,'{"fixture":"integration-bind"}'::jsonb
)
RETURNING id::text
`, account.AccountID, emailDigest, h.now).Scan(&emailCredentialID)
		if err != nil {
			t.Fatalf("bind email credential: %v", err)
		}
		exerciseAuthoritativeSecurityLifecycle(t, instance, account.AccountID, h.now)
		assertIdentityAccountSecurityRLS(t, h, instance, account.AccountID, h.now)

		orgID := "10000000-0000-4000-8000-000000000001"
		workspaceID := "10000000-0000-4000-8000-000000000002"
		projectID := "10000000-0000-4000-8000-000000000003"
		mustExecArgs(t, instance.adminDB,
			`INSERT INTO organizations(id,slug,display_name) VALUES ($1::uuid,'identity-org','Identity Org')`,
			orgID,
		)
		mustExecArgs(t, instance.adminDB,
			`INSERT INTO workspaces(id,organization_id,slug,display_name) VALUES ($1::uuid,$2::uuid,'identity-workspace','Identity Workspace')`,
			workspaceID, orgID,
		)
		mustExecArgs(t, instance.adminDB, `
INSERT INTO projects(id,organization_id,workspace_id,slug,display_name)
VALUES ($1::uuid,$2::uuid,$3::uuid,'identity-project','Identity Project')
`, projectID, orgID, workspaceID)
		var orgMembershipID string
		err = instance.adminDB.QueryRow(`
INSERT INTO identity_organization_memberships(
  organization_id,principal_id,role,status,activated_at
) VALUES ($1::uuid,$2::uuid,'owner','active',$3)
RETURNING id::text
`, orgID, account.AccountID, h.now).Scan(&orgMembershipID)
		if err != nil {
			t.Fatal(err)
		}
		mustExecArgs(t, instance.adminDB, `
INSERT INTO identity_project_memberships(
  organization_id,project_id,principal_id,organization_membership_id,role,status,activated_at
) VALUES ($1::uuid,$2::uuid,$3::uuid,$4::uuid,'admin','active',$5)
`, orgID, projectID, account.AccountID, orgMembershipID, h.now)

		login := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation: IdentityOperationLogin, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "owner@example.cn",
		})
		auth, err := instance.service.CompleteLogin(completionFor(login))
		if err != nil {
			t.Fatal(err)
		}
		if auth.Credential.CredentialID != emailCredentialID || auth.Credential.Provider != IdentityProviderLocal {
			t.Fatalf("login did not return exact authenticating credential: %#v", auth.Credential)
		}
		if auth.Account.CredentialCount != 2 || auth.Account.SecurityPosture.Password.Status != "set" ||
			auth.Account.SecurityPosture.TwoFactor.Status != "enabled" || auth.Account.MembershipCount != 2 {
			t.Fatalf("canonical projection is incomplete: %#v", auth.Account)
		}
		assertPublicIdentityJSON(t, auth)
	})

	t.Run("restricted scoped identity security ticket issuer", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		instance := h.newInstance(
			t,
			[]byte("scoped-security-issuer-key-0123456789"),
			"v1",
			nil,
		)
		registration := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation:     IdentityOperationRegistration,
			Kind:          IdentityCredentialEmail,
			Provider:      IdentityProviderLocal,
			Identifier:    "security-issuer-owner@qq.com",
			VerifiedEmail: "security-issuer-owner@qq.com",
			DisplayName:   "Security Issuer Owner",
		})
		account, err := instance.service.CompleteRegistration(
			completionFor(registration),
		)
		if err != nil {
			t.Fatalf("register security issuer account: %v", err)
		}
		orgID := "18000000-0000-4000-8000-000000000001"
		workspaceID := "18000000-0000-4000-8000-000000000002"
		projectID := "18000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t,
			instance,
			account.AccountID,
			orgID,
			workspaceID,
			projectID,
			h.now,
		)
		sessionID, sessionDigest := issueScopedIdentitySession(
			t,
			instance,
			account.AccountID,
			account.Credentials[0].CredentialID,
			orgID,
			projectID,
			h.now,
		)

		issuerDB, err := sql.Open("postgres", h.issuerDSN)
		if err != nil {
			t.Fatalf("open restricted issuer database: %v", err)
		}
		issuerDB.SetMaxOpenConns(16)
		t.Cleanup(func() { _ = issuerDB.Close() })
		issuer, err := NewProductionIdentitySecurityTicketIssuer(
			ProductionIdentitySecurityTicketIssuerOptions{
				DB:               issuerDB,
				SQLTimeout:       10 * time.Second,
				StatementTimeout: 8 * time.Second,
				LockTimeout:      5 * time.Second,
			},
		)
		if err != nil {
			t.Fatalf("construct restricted issuer: %v", err)
		}
		if err := issuer.Ready(context.Background()); err != nil {
			t.Fatalf("restricted issuer readiness: %v", err)
		}

		now := time.Now().UTC()
		request := IdentitySecurityTicketIssueRequest{
			OrganizationID: orgID,
			ProjectID:      projectID,
			AccountID:      account.AccountID,
			ActorID:        account.AccountID,
			SessionID:      sessionID,
			SessionDigest:  sessionDigest,
			Operation:      "password_change",
			IdempotencyKey: "restricted-issuer-password-change",
			SecretRef:      "isr_" + strings.Repeat("A", 24),
			SecretDigest:   strings.Repeat("a", 64),
			ExpiresAt:      now.Add(4 * time.Minute),
		}
		request.ContextDigest = identitySecurityTicketContextDigest(request)
		issued, err := issuer.IssueIdentitySecurityMutationTicket(
			context.Background(),
			request,
		)
		if err != nil {
			t.Fatalf("issue restricted security ticket: %v", err)
		}

		retryRequest := request
		retryRequest.ExpiresAt = now.Add(5 * time.Minute)
		retry, err := issuer.IssueIdentitySecurityMutationTicket(
			context.Background(),
			retryRequest,
		)
		if err != nil {
			t.Fatalf("exact issuer retry: %v", err)
		}
		if retry != issued {
			t.Fatalf("exact issuer retry changed projection: first=%#v retry=%#v", issued, retry)
		}

		const concurrentRetries = 12
		results := make(chan IdentitySecurityIssuedTicket, concurrentRetries)
		failures := make(chan error, concurrentRetries)
		var wait sync.WaitGroup
		for index := 0; index < concurrentRetries; index++ {
			wait.Add(1)
			go func() {
				defer wait.Done()
				result, issueErr := issuer.IssueIdentitySecurityMutationTicket(
					context.Background(),
					retryRequest,
				)
				if issueErr != nil {
					failures <- issueErr
					return
				}
				results <- result
			}()
		}
		wait.Wait()
		close(results)
		close(failures)
		for issueErr := range failures {
			t.Fatalf("concurrent exact issuer retry: %v", issueErr)
		}
		for result := range results {
			if result != issued {
				t.Fatalf("concurrent retry changed issuer projection: %#v", result)
			}
		}

		conflict := request
		conflict.SecretDigest = strings.Repeat("b", 64)
		if _, err := issuer.IssueIdentitySecurityMutationTicket(
			context.Background(),
			conflict,
		); err == nil {
			t.Fatal("issuer accepted conflicting retry")
		}

		for _, testCase := range []struct {
			name   string
			mutate func(*IdentitySecurityTicketIssueRequest)
		}{
			{
				name: "organization",
				mutate: func(candidate *IdentitySecurityTicketIssueRequest) {
					candidate.OrganizationID =
						"19000000-0000-4000-8000-000000000001"
				},
			},
			{
				name: "project",
				mutate: func(candidate *IdentitySecurityTicketIssueRequest) {
					candidate.ProjectID =
						"19000000-0000-4000-8000-000000000003"
				},
			},
			{
				name: "principal",
				mutate: func(candidate *IdentitySecurityTicketIssueRequest) {
					candidate.AccountID =
						"19000000-0000-4000-8000-000000000004"
					candidate.ActorID = candidate.AccountID
				},
			},
			{
				name: "session",
				mutate: func(candidate *IdentitySecurityTicketIssueRequest) {
					candidate.SessionID =
						"19000000-0000-4000-8000-000000000005"
				},
			},
			{
				name: "session digest",
				mutate: func(candidate *IdentitySecurityTicketIssueRequest) {
					candidate.SessionDigest = strings.Repeat("f", 64)
				},
			},
		} {
			t.Run("reject "+testCase.name+" mismatch", func(t *testing.T) {
				candidate := request
				candidate.IdempotencyKey = "reject-" +
					strings.ReplaceAll(testCase.name, " ", "-") + "-mismatch"
				testCase.mutate(&candidate)
				candidate.ContextDigest = identitySecurityTicketContextDigest(candidate)
				if _, issueErr := issuer.IssueIdentitySecurityMutationTicket(
					context.Background(),
					candidate,
				); issueErr == nil {
					t.Fatalf("issuer accepted %s mismatch", testCase.name)
				}
			})
		}

		if err := issuer.CancelIdentitySecurityMutationTicket(
			context.Background(),
			request,
			issued,
		); err != nil {
			t.Fatalf("cancel issued ticket: %v", err)
		}
		if err := issuer.CancelIdentitySecurityMutationTicket(
			context.Background(),
			request,
			issued,
		); err != nil {
			t.Fatalf("idempotent ticket cancellation: %v", err)
		}
		if _, err := issuer.IssueIdentitySecurityMutationTicket(
			context.Background(),
			request,
		); err == nil {
			t.Fatal("canceled issuer idempotency key was reused")
		}

		recoveryRequest := request
		recoveryRequest.Operation = "password_recovery"
		recoveryRequest.IdempotencyKey = "verified-email-password-recovery"
		recoveryRequest.SecretRef = "isr_" + strings.Repeat("R", 24)
		recoveryRequest.SecretDigest = strings.Repeat("c", 64)
		recoveryRequest.ExpiresAt = time.Now().UTC().Add(4 * time.Minute)
		recoveryRequest.ContextDigest =
			identitySecurityTicketContextDigest(recoveryRequest)
		recoveryIssued, err := issuer.IssueIdentitySecurityMutationTicket(
			context.Background(),
			recoveryRequest,
		)
		if err != nil {
			t.Fatalf("verified email recovery ticket: %v", err)
		}
		if err := issuer.CancelIdentitySecurityMutationTicket(
			context.Background(),
			recoveryRequest,
			recoveryIssued,
		); err != nil {
			t.Fatalf("cancel recovery ticket: %v", err)
		}

		oauthRegistration := issueLifecycleProof(
			t,
			instance.service,
			TrustedIdentityProof{
				Operation:   IdentityOperationRegistration,
				Kind:        IdentityCredentialOAuth,
				Provider:    IdentityProviderGoogle,
				Identifier:  "security-issuer-google-subject",
				DisplayName: "OAuth Recovery Rejection",
			},
		)
		oauthAccount, err := instance.service.CompleteRegistration(
			completionFor(oauthRegistration),
		)
		if err != nil {
			t.Fatalf("register OAuth-only account: %v", err)
		}
		oauthOrgID := "1a000000-0000-4000-8000-000000000001"
		oauthWorkspaceID := "1a000000-0000-4000-8000-000000000002"
		oauthProjectID := "1a000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t,
			instance,
			oauthAccount.AccountID,
			oauthOrgID,
			oauthWorkspaceID,
			oauthProjectID,
			h.now,
		)
		oauthSessionID, oauthSessionDigest := issueScopedIdentitySession(
			t,
			instance,
			oauthAccount.AccountID,
			oauthAccount.Credentials[0].CredentialID,
			oauthOrgID,
			oauthProjectID,
			h.now,
		)
		oauthRecovery := recoveryRequest
		oauthRecovery.OrganizationID = oauthOrgID
		oauthRecovery.ProjectID = oauthProjectID
		oauthRecovery.AccountID = oauthAccount.AccountID
		oauthRecovery.ActorID = oauthAccount.AccountID
		oauthRecovery.SessionID = oauthSessionID
		oauthRecovery.SessionDigest = oauthSessionDigest
		oauthRecovery.IdempotencyKey = "oauth-only-recovery-rejected"
		oauthRecovery.ExpiresAt = time.Now().UTC().Add(4 * time.Minute)
		oauthRecovery.ContextDigest =
			identitySecurityTicketContextDigest(oauthRecovery)
		if _, err := issuer.IssueIdentitySecurityMutationTicket(
			context.Background(),
			oauthRecovery,
		); err == nil {
			t.Fatal("OAuth-only session issued a password recovery ticket")
		}

		for name, query := range map[string]string{
			"runtime issue": `
SELECT a1_issue_scoped_identity_security_mutation_ticket(
  $1::uuid,$2::uuid,$3::uuid,$3::uuid,$4::uuid,$5,
  'password_change','runtime-must-not-issue',$6,$7,$8,NULL,NULL,$9
)`,
			"runtime cancel": `
SELECT a1_cancel_scoped_identity_security_mutation_ticket(
  $1::uuid,$2::uuid,$3::uuid,$3::uuid,$4::uuid,
  'password_change','restricted-issuer-password-change',$5,$6,$7
)`,
		} {
			t.Run(name+" authority denied", func(t *testing.T) {
				var discarded any
				args := []any{
					orgID,
					projectID,
					account.AccountID,
					sessionID,
					sessionDigest,
					request.ContextDigest,
					request.SecretRef,
					request.SecretDigest,
					time.Now().UTC().Add(4 * time.Minute),
				}
				if name == "runtime cancel" {
					args = []any{
						orgID,
						projectID,
						account.AccountID,
						sessionID,
						request.ContextDigest,
						issued.TicketID,
						issued.ReceiptID,
					}
				}
				if queryErr := instance.db.QueryRow(query, args...).Scan(&discarded); queryErr == nil {
					t.Fatalf("%s unexpectedly succeeded", name)
				}
			})
		}
		if _, err := instance.db.Exec(
			`SELECT count(*) FROM identity_security_ticket_issuance`,
		); err == nil {
			t.Fatal("runtime role read issuer audit table")
		}
		for name, query := range map[string]string{
			"project security": `SELECT a1_project_account_security($1::uuid)`,
			"resolve ticket": `
SELECT a1_resolve_identity_security_mutation_ticket($1,$2,$3,$4::uuid,clock_timestamp())
`,
			"execute mutation": `
SELECT a1_execute_identity_security_mutation($1,$2,$3,$4::uuid)
`,
			"issuer table": `SELECT count(*) FROM identity_security_ticket_issuance`,
		} {
			t.Run("issuer cannot "+name, func(t *testing.T) {
				var discarded any
				var queryErr error
				switch name {
				case "project security":
					queryErr = issuerDB.QueryRow(query, account.AccountID).Scan(&discarded)
				case "resolve ticket":
					queryErr = issuerDB.QueryRow(
						query,
						issued.TicketID,
						issued.ReceiptID,
						issued.ContextDigest,
						account.AccountID,
					).Scan(&discarded)
				case "execute mutation":
					queryErr = issuerDB.QueryRow(
						query,
						issued.TicketID,
						issued.ReceiptID,
						"restricted-issuer-password-change",
						account.AccountID,
					).Scan(&discarded)
				default:
					queryErr = issuerDB.QueryRow(query).Scan(&discarded)
				}
				if queryErr == nil {
					t.Fatalf("issuer unexpectedly accessed %s", name)
				}
			})
		}

		var rlsEnabled, rlsForced, issuerNoLogin, issuerRestricted bool
		if err := instance.adminDB.QueryRow(`
SELECT
  table_class.relrowsecurity,
  table_class.relforcerowsecurity,
  NOT issuer_role.rolcanlogin,
  NOT issuer_role.rolsuper
    AND NOT issuer_role.rolbypassrls
    AND NOT issuer_role.rolinherit
FROM pg_class AS table_class
JOIN pg_roles AS issuer_role
  ON issuer_role.rolname='a1_security_ticket_issuer'
WHERE table_class.oid='identity_security_ticket_issuance'::regclass
`).Scan(
			&rlsEnabled,
			&rlsForced,
			&issuerNoLogin,
			&issuerRestricted,
		); err != nil {
			t.Fatalf("inspect issuer RLS and role posture: %v", err)
		}
		if !rlsEnabled || !rlsForced || !issuerNoLogin || !issuerRestricted {
			t.Fatalf(
				"unsafe issuer posture rls=%t force=%t no_login=%t restricted=%t",
				rlsEnabled,
				rlsForced,
				issuerNoLogin,
				issuerRestricted,
			)
		}
	})

	t.Run("atomic credential link and exact replay", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		instance := h.newInstance(t, []byte("credential-link-key-012345678901234"), "v1", nil)
		registration := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "link-owner@example.cn",
			VerifiedEmail: "link-owner@example.cn", DisplayName: "Credential Link Owner",
		})
		account, err := instance.service.CompleteRegistration(completionFor(registration))
		if err != nil {
			t.Fatal(err)
		}
		if len(account.Credentials) != 1 {
			t.Fatalf("registration returned credentials=%d want=1", len(account.Credentials))
		}

		orgID := "20000000-0000-4000-8000-000000000001"
		workspaceID := "20000000-0000-4000-8000-000000000002"
		projectID := "20000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t, instance, account.AccountID, orgID, workspaceID, projectID, h.now,
		)
		sessionID, sessionDigest := issueScopedIdentitySession(
			t, instance, account.AccountID, account.Credentials[0].CredentialID,
			orgID, projectID, h.now,
		)
		proof := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation: IdentityOperationCredentialLink, Kind: IdentityCredentialOAuth,
			Provider: IdentityProviderGoogle, Identifier: "google-link-subject",
			VerifiedEmail: "link-owner@example.cn",
			TenantID:      orgID, ProjectID: projectID,
		})
		command := authorizeIdentityCredentialLink(
			t, instance, account.AccountID, sessionID, sessionDigest,
			orgID, projectID, proof, "credential-link-integration", h.now,
		)

		result, err := instance.credentialLinkService.Complete(context.Background(), command)
		if err != nil {
			t.Fatalf("complete credential link: %v", err)
		}
		if result.SchemaVersion != IdentityCredentialLinkSchemaVersion ||
			result.AccountID != account.AccountID ||
			result.Credential.Provider != IdentityProviderGoogle ||
			!result.Credential.Verified || !result.CredentialAdded ||
			result.LinkedAt.IsZero() {
			t.Fatalf("credential link returned %#v", result)
		}
		assertPublicIdentityJSON(t, result)
		encoded, err := json.Marshal(result)
		if err != nil {
			t.Fatal(err)
		}
		for _, secret := range []string{
			proof.ReceiptID, command.SessionDigest, command.MutationTicketID,
			command.StepUpReceiptID, "google-link-subject", "link-owner@example.cn",
		} {
			if strings.Contains(string(encoded), secret) {
				t.Fatalf("credential link result leaked trusted material %q: %s", secret, encoded)
			}
		}

		replay, err := instance.credentialLinkService.Complete(context.Background(), command)
		if err != nil {
			t.Fatalf("exact credential link replay: %v", err)
		}
		if replay.CredentialAdded ||
			replay.Credential.CredentialID != result.Credential.CredentialID ||
			!replay.LinkedAt.Equal(result.LinkedAt) {
			t.Fatalf("exact replay changed result: first=%#v replay=%#v", result, replay)
		}
		changedRequests := map[string]func(*IdentityCredentialLinkCommand){
			"idempotency": func(item *IdentityCredentialLinkCommand) {
				item.IdempotencyKey = "credential-link-integration-changed"
			},
			"request fingerprint": func(item *IdentityCredentialLinkCommand) {
				item.SessionID = "different-trusted-session-id"
			},
		}
		for name, mutate := range changedRequests {
			t.Run(name+" conflict is public safe", func(t *testing.T) {
				changed := command
				mutate(&changed)
				_, changedErr := instance.credentialLinkService.Complete(
					context.Background(), changed,
				)
				var domain IdentityDomainError
				if !errors.As(changedErr, &domain) ||
					domain.Code != "identity_credential_link_conflict" {
					t.Fatalf("changed replay returned %v", changedErr)
				}
				if strings.Contains(changedErr.Error(), "identity_credential_link_idempotency_conflict") {
					t.Fatalf("changed replay leaked PostgreSQL detail: %v", changedErr)
				}
			})
		}
		var credentials, consumedProofs, consumedTickets, consumedReceipts, events int
		if err := instance.adminDB.QueryRow(`
SELECT
  (SELECT count(*) FROM identity_credentials WHERE principal_id=$1::uuid),
  (SELECT count(*) FROM identity_lifecycle_receipts
    WHERE receipt_digest=$2 AND consumed_at IS NOT NULL),
  (SELECT count(*) FROM identity_security_mutation_tickets
    WHERE ticket_digest=$3 AND consumed_at IS NOT NULL),
  (SELECT count(*) FROM identity_security_receipts
    WHERE receipt_digest=$4 AND consumed_at IS NOT NULL),
  (SELECT count(*) FROM identity_audit_events
    WHERE principal_id=$1::uuid AND action='identity.credential.link.completed')
`, account.AccountID, instance.receipts.receiptDigest(proof.ReceiptID),
			command.MutationTicketID, command.StepUpReceiptID).
			Scan(&credentials, &consumedProofs, &consumedTickets, &consumedReceipts, &events); err != nil {
			t.Fatal(err)
		}
		if credentials != 2 || consumedProofs != 1 || consumedTickets != 1 ||
			consumedReceipts != 1 || events != 1 {
			t.Fatalf(
				"credential link counts credentials=%d proof=%d ticket=%d step_up=%d events=%d",
				credentials, consumedProofs, consumedTickets, consumedReceipts, events,
			)
		}
	})

	t.Run("credential link replay survives encryption key retirement", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		oldEncryption := []byte("old-link-encryption-0123456789012345")
		newEncryption := []byte("new-link-encryption-0123456789012345")
		stableLookup := []byte("stable-link-lookup-012345678901234567")
		newLookup := []byte("new-link-lookup-012345678901234567890")
		old := h.newInstanceWithLifecycleKeys(
			t, oldEncryption, "enc-old", nil,
			stableLookup, "lookup-v1", nil,
		)
		registration := issueLifecycleProof(t, old.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "rotated-link@example.cn",
			VerifiedEmail: "rotated-link@example.cn", DisplayName: "Rotated Link Owner",
		})
		account, err := old.service.CompleteRegistration(completionFor(registration))
		if err != nil {
			t.Fatal(err)
		}
		orgID := "25000000-0000-4000-8000-000000000001"
		workspaceID := "25000000-0000-4000-8000-000000000002"
		projectID := "25000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t, old, account.AccountID, orgID, workspaceID, projectID, h.now,
		)
		sessionID, sessionDigest := issueScopedIdentitySession(
			t, old, account.AccountID, account.Credentials[0].CredentialID,
			orgID, projectID, h.now,
		)
		proof := issueLifecycleProof(t, old.service, TrustedIdentityProof{
			Operation: IdentityOperationCredentialLink, Kind: IdentityCredentialOAuth,
			Provider: IdentityProviderGoogle, Identifier: "rotated-google-subject",
			VerifiedEmail: "rotated-link@example.cn",
			TenantID:      orgID, ProjectID: projectID,
		})
		command := authorizeIdentityCredentialLink(
			t, old, account.AccountID, sessionID, sessionDigest,
			orgID, projectID, proof, "credential-link-key-retirement", h.now,
		)
		first, err := old.credentialLinkService.Complete(context.Background(), command)
		if err != nil {
			t.Fatal(err)
		}

		retired := h.newInstanceWithLifecycleKeys(
			t, newEncryption, "enc-new", nil,
			newLookup, "lookup-v2", []IdentityLifecycleLookupKey{{
				Version: "lookup-v1", Key: stableLookup,
			}},
		)
		replay, err := retired.credentialLinkService.Complete(context.Background(), command)
		if err != nil {
			t.Fatalf("completed replay failed after old encryption key retirement: %v", err)
		}
		if replay.CredentialAdded ||
			replay.Credential.CredentialID != first.Credential.CredentialID ||
			!replay.LinkedAt.Equal(first.LinkedAt) {
			t.Fatalf("retired-key replay changed result: first=%#v replay=%#v", first, replay)
		}

		pendingProof := issueLifecycleProof(t, old.service, TrustedIdentityProof{
			Operation: IdentityOperationCredentialLink, Kind: IdentityCredentialOAuth,
			Provider: IdentityProviderGitHub, Identifier: "retired-github-subject",
			VerifiedEmail: "rotated-link@example.cn",
			TenantID:      orgID, ProjectID: projectID,
		})
		pendingCommand := authorizeIdentityCredentialLink(
			t, old, account.AccountID, sessionID, sessionDigest,
			orgID, projectID, pendingProof, "credential-link-pending-retirement", h.now,
		)
		readiness, err := retired.store.LifecycleReceiptLookupRetirementReadiness(
			context.Background(), "lookup-v1",
		)
		if err != nil {
			t.Fatalf("lookup retirement preflight failed: %v", err)
		}
		if readiness.Ready ||
			readiness.ActiveVersion != "lookup-v2" ||
			readiness.RetiringVersion != "lookup-v1" ||
			readiness.RetiringLiveReceipts == 0 ||
			readiness.RetiringReplayRecords == 0 ||
			readiness.UnreachableLiveReceipts == 0 ||
			readiness.UnreachableReplayRecords == 0 ||
			readiness.LiveReceiptsRequiredUntil == nil ||
			!readiness.ReplayRetentionRequired {
			t.Fatalf("unsafe lookup retirement was not blocked: %#v", readiness)
		}
		var completedLookupVersion, pendingLookupVersion string
		if err := old.adminDB.QueryRow(`
SELECT
  (SELECT lookup_key_version FROM identity_lifecycle_receipts
    WHERE receipt_digest=$1),
  (SELECT lookup_key_version FROM identity_lifecycle_receipts
    WHERE receipt_digest=$2)
`, old.receipts.receiptDigest(proof.ReceiptID),
			old.receipts.receiptDigest(pendingProof.ReceiptID)).
			Scan(&completedLookupVersion, &pendingLookupVersion); err != nil {
			t.Fatal(err)
		}
		if completedLookupVersion != "lookup-v1" ||
			pendingLookupVersion != "lookup-v1" {
			t.Fatalf(
				"receipt lookup versions completed=%q pending=%q",
				completedLookupVersion, pendingLookupVersion,
			)
		}
		_, err = retired.credentialLinkService.Complete(context.Background(), pendingCommand)
		var domain IdentityDomainError
		if !errors.As(err, &domain) || domain.Code != "identity_credential_link_unavailable" {
			t.Fatalf("unconsumed retired-key proof returned %v", err)
		}
		if strings.Contains(err.Error(), "enc-old") ||
			strings.Contains(err.Error(), ErrIdentityProofKeyUnavailable.Error()) {
			t.Fatalf("retired-key failure leaked internal key detail: %v", err)
		}
		if _, err := old.credentialLinkService.Complete(context.Background(), pendingCommand); err != nil {
			t.Fatalf("retired-key failure consumed authorization artifacts: %v", err)
		}

		var credentials, completedEvents int
		if err := old.adminDB.QueryRow(`
SELECT
  (SELECT count(*) FROM identity_credentials WHERE principal_id=$1::uuid),
  (SELECT count(*) FROM identity_audit_events
    WHERE principal_id=$1::uuid AND action='identity.credential.link.completed')
`, account.AccountID).Scan(&credentials, &completedEvents); err != nil {
			t.Fatal(err)
		}
		if credentials != 3 || completedEvents != 2 {
			t.Fatalf(
				"retired-key replay duplicated state credentials=%d completed_events=%d",
				credentials, completedEvents,
			)
		}
	})

	t.Run("credential link replay purge is bounded idempotent and aggregate only", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		instance := h.newInstanceWithLifecycleKeys(
			t, []byte("purge-encryption-0123456789012345678"), "enc-v1", nil,
			[]byte("purge-new-lookup-012345678901234567890"), "lookup-v2",
			[]IdentityLifecycleLookupKey{{
				Version: "lookup-v1",
				Key:     []byte("purge-old-lookup-012345678901234567890"),
			}},
		)
		registration := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "replay-purge@example.cn",
			VerifiedEmail: "replay-purge@example.cn", DisplayName: "Replay Purge Owner",
		})
		account, err := instance.service.CompleteRegistration(completionFor(registration))
		if err != nil {
			t.Fatal(err)
		}
		historicalConsumedAt := h.now.Add(-31 * 24 * time.Hour)
		historicalExpiresAt := historicalConsumedAt.Add(-time.Minute)
		mustExecArgs(t, instance.adminDB, `
INSERT INTO identity_lifecycle_receipts(
  receipt_digest,operation,provider,tenant_scope,project_scope,
  proof_nonce,proof_key_version,lookup_key_version,proof_ciphertext,
  expires_at,consumed_at,consume_outcome,
  link_idempotency_digest,link_request_digest,link_result_id
) VALUES (
  $1,'credential_link','google','','',
  decode($2,'hex'),'enc-v1','lookup-v1',decode($3,'hex'),
  $4,$5,'success',$6,$7,$8::uuid
)
`, strings.Repeat("1", 64), strings.Repeat("ab", 12),
			strings.Repeat("cd", 32), historicalExpiresAt,
			historicalConsumedAt, strings.Repeat("2", 64),
			strings.Repeat("3", 64), account.Credentials[0].CredentialID)

		readiness, err := instance.store.LifecycleReceiptLookupRetirementReadiness(
			context.Background(), "lookup-v1",
		)
		if err != nil {
			t.Fatal(err)
		}
		if readiness.Ready || readiness.RetiringReplayRecords != 1 ||
			!readiness.ReplayRetentionRequired {
			t.Fatalf("historical replay did not block retirement: %#v", readiness)
		}

		beforeDeadline, err := instance.store.PurgeExpiredCredentialLinkReplays(
			context.Background(), IdentityCredentialLinkReplayPurgeRequest{
				Cutoff:  historicalConsumedAt.Add(29 * 24 * time.Hour),
				MaxRows: 1, Actor: "中国区身份运维",
				Reason: "保留期前验证", IdempotencyKey: "before-retention",
			},
		)
		if err != nil {
			t.Fatal(err)
		}
		if beforeDeadline.PurgedRows != 0 ||
			len(beforeDeadline.LookupVersionCounts) != 0 {
			t.Fatalf("pre-retention purge removed replay: %#v", beforeDeadline)
		}

		request := IdentityCredentialLinkReplayPurgeRequest{
			Cutoff: h.now, MaxRows: 1, Actor: "中国区身份运维",
			Reason: "已过保留期且密钥轮换", IdempotencyKey: "retire-lookup-v1",
		}
		first, err := instance.store.PurgeExpiredCredentialLinkReplays(
			context.Background(), request,
		)
		if err != nil {
			t.Fatal(err)
		}
		if first.PurgedRows != 1 ||
			first.LookupVersionCounts["lookup-v1"] != 1 {
			t.Fatalf("eligible replay was not purged: %#v", first)
		}
		replay, err := instance.store.PurgeExpiredCredentialLinkReplays(
			context.Background(), request,
		)
		if err != nil {
			t.Fatal(err)
		}
		if replay.PurgeID != first.PurgeID ||
			replay.PurgedRows != first.PurgedRows ||
			!replay.CompletedAt.Equal(first.CompletedAt) {
			t.Fatalf("purge replay changed receipt: first=%#v replay=%#v", first, replay)
		}
		conflict := request
		conflict.Reason = "changed request"
		if _, err := instance.store.PurgeExpiredCredentialLinkReplays(
			context.Background(), conflict,
		); err == nil || !strings.Contains(err.Error(), "idempotency") {
			t.Fatalf("changed purge request did not conflict: %v", err)
		}

		readiness, err = instance.store.LifecycleReceiptLookupRetirementReadiness(
			context.Background(), "lookup-v1",
		)
		if err != nil {
			t.Fatal(err)
		}
		if !readiness.Ready || readiness.RetiringReplayRecords != 0 ||
			readiness.ReplayRetentionRequired {
			t.Fatalf("purge did not unblock lookup retirement: %#v", readiness)
		}

		var auditRows int
		var auditText string
		if err := instance.adminDB.QueryRow(`
SELECT count(*),string_agg(to_jsonb(a)::text,'')
FROM identity_credential_link_replay_purge_audit AS a
`).Scan(&auditRows, &auditText); err != nil {
			t.Fatal(err)
		}
		if auditRows != 2 {
			t.Fatalf("purge audit rows=%d want=2", auditRows)
		}
		for _, forbidden := range []string{
			"proof_nonce", "proof_ciphertext", "receipt_digest",
			"link_result_id", account.Credentials[0].CredentialID,
		} {
			if strings.Contains(auditText, forbidden) {
				t.Fatalf("purge audit leaked %q: %s", forbidden, auditText)
			}
		}
		if _, err := instance.db.Exec(
			`DELETE FROM identity_credential_link_replay_purge_audit`,
		); err == nil {
			t.Fatal("runtime directly deleted purge audit")
		}
		if _, err := instance.db.Exec(
			`DELETE FROM identity_lifecycle_receipts`,
		); err == nil {
			t.Fatal("runtime directly deleted lifecycle receipts")
		}
	})

	t.Run("concurrent credential link is one mutation with stable replay", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		key := []byte("concurrent-link-key-012345678901234")
		first := h.newInstance(t, key, "v1", nil)
		second := h.newInstance(t, key, "v1", nil)
		registration := issueLifecycleProof(t, first.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "concurrent-link@example.cn",
			VerifiedEmail: "concurrent-link@example.cn", DisplayName: "Concurrent Link Owner",
		})
		account, err := first.service.CompleteRegistration(completionFor(registration))
		if err != nil {
			t.Fatal(err)
		}
		orgID := "30000000-0000-4000-8000-000000000001"
		workspaceID := "30000000-0000-4000-8000-000000000002"
		projectID := "30000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t, first, account.AccountID, orgID, workspaceID, projectID, h.now,
		)
		sessionID, sessionDigest := issueScopedIdentitySession(
			t, first, account.AccountID, account.Credentials[0].CredentialID,
			orgID, projectID, h.now,
		)
		proof := issueLifecycleProof(t, first.service, TrustedIdentityProof{
			Operation: IdentityOperationCredentialLink, Kind: IdentityCredentialOAuth,
			Provider: IdentityProviderGitHub, Identifier: "concurrent-github-subject",
			VerifiedEmail: "concurrent-link@example.cn",
			TenantID:      orgID, ProjectID: projectID,
		})
		command := authorizeIdentityCredentialLink(
			t, first, account.AccountID, sessionID, sessionDigest,
			orgID, projectID, proof, "credential-link-concurrent", h.now,
		)

		type completion struct {
			result IdentityCredentialLinkResultDTO
			err    error
		}
		const completions = 16
		responses := make(chan completion, completions)
		var wait sync.WaitGroup
		for index := 0; index < completions; index++ {
			wait.Add(1)
			go func(index int) {
				defer wait.Done()
				service := first.credentialLinkService
				if index%2 == 1 {
					service = second.credentialLinkService
				}
				result, err := service.Complete(context.Background(), command)
				responses <- completion{result: result, err: err}
			}(index)
		}
		wait.Wait()
		close(responses)

		var credentialID string
		var linkedAt time.Time
		added := 0
		replayed := 0
		for response := range responses {
			if response.err != nil {
				t.Fatalf("concurrent credential link returned %v", response.err)
			}
			if response.result.CredentialAdded {
				added++
			} else {
				replayed++
			}
			if credentialID == "" {
				credentialID = response.result.Credential.CredentialID
				linkedAt = response.result.LinkedAt
				continue
			}
			if response.result.Credential.CredentialID != credentialID ||
				!response.result.LinkedAt.Equal(linkedAt) {
				t.Fatalf(
					"concurrent replay changed result: credential=%q/%q linked_at=%s/%s",
					credentialID, response.result.Credential.CredentialID,
					linkedAt, response.result.LinkedAt,
				)
			}
		}
		if added != 1 || replayed != completions-1 {
			t.Fatalf("concurrent completion added=%d replayed=%d", added, replayed)
		}

		var credentials, consumedProofs, consumedTickets, consumedReceipts, events int
		if err := first.adminDB.QueryRow(`
SELECT
  (SELECT count(*) FROM identity_credentials WHERE principal_id=$1::uuid),
  (SELECT count(*) FROM identity_lifecycle_receipts
    WHERE receipt_digest=$2 AND consumed_at IS NOT NULL),
  (SELECT count(*) FROM identity_security_mutation_tickets
    WHERE ticket_digest=$3 AND consumed_at IS NOT NULL),
  (SELECT count(*) FROM identity_security_receipts
    WHERE receipt_digest=$4 AND consumed_at IS NOT NULL),
  (SELECT count(*) FROM identity_audit_events
    WHERE principal_id=$1::uuid AND action='identity.credential.link.completed')
`, account.AccountID, first.receipts.receiptDigest(proof.ReceiptID),
			command.MutationTicketID, command.StepUpReceiptID).
			Scan(&credentials, &consumedProofs, &consumedTickets, &consumedReceipts, &events); err != nil {
			t.Fatal(err)
		}
		if credentials != 2 || consumedProofs != 1 || consumedTickets != 1 ||
			consumedReceipts != 1 || events != 1 {
			t.Fatalf(
				"concurrent credential link counts credentials=%d proof=%d ticket=%d step_up=%d events=%d",
				credentials, consumedProofs, consumedTickets, consumedReceipts, events,
			)
		}
	})

	t.Run("provider subject conflict rolls back cross-account takeover", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		instance := h.newInstance(t, []byte("subject-conflict-key-01234567890123"), "v1", nil)
		register := func(email, displayName string) IdentityAccountDTO {
			t.Helper()
			proof := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
				Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
				Provider: IdentityProviderLocal, Identifier: email,
				VerifiedEmail: email, DisplayName: displayName,
			})
			account, err := instance.service.CompleteRegistration(completionFor(proof))
			if err != nil {
				t.Fatalf("register %s: %v", email, err)
			}
			return account
		}
		owner := register("subject-owner@example.cn", "Subject Owner")
		attacker := register("subject-attacker@example.cn", "Subject Attacker")

		ownerOrgID := "40000000-0000-4000-8000-000000000001"
		ownerWorkspaceID := "40000000-0000-4000-8000-000000000002"
		ownerProjectID := "40000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t, instance, owner.AccountID,
			ownerOrgID, ownerWorkspaceID, ownerProjectID, h.now,
		)
		ownerSessionID, ownerSessionDigest := issueScopedIdentitySession(
			t, instance, owner.AccountID, owner.Credentials[0].CredentialID,
			ownerOrgID, ownerProjectID, h.now,
		)
		ownerProof := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation: IdentityOperationCredentialLink, Kind: IdentityCredentialOAuth,
			Provider: IdentityProviderGoogle, Identifier: "globally-unique-google-subject",
			VerifiedEmail: "subject-owner@example.cn",
			TenantID:      ownerOrgID, ProjectID: ownerProjectID,
		})
		ownerCommand := authorizeIdentityCredentialLink(
			t, instance, owner.AccountID, ownerSessionID, ownerSessionDigest,
			ownerOrgID, ownerProjectID, ownerProof, "subject-owner-link", h.now,
		)
		if _, err := instance.credentialLinkService.Complete(
			context.Background(), ownerCommand,
		); err != nil {
			t.Fatalf("owner credential link: %v", err)
		}

		attackerOrgID := "50000000-0000-4000-8000-000000000001"
		attackerWorkspaceID := "50000000-0000-4000-8000-000000000002"
		attackerProjectID := "50000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t, instance, attacker.AccountID,
			attackerOrgID, attackerWorkspaceID, attackerProjectID, h.now,
		)
		attackerSessionID, attackerSessionDigest := issueScopedIdentitySession(
			t, instance, attacker.AccountID, attacker.Credentials[0].CredentialID,
			attackerOrgID, attackerProjectID, h.now,
		)
		attackerProof := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation: IdentityOperationCredentialLink, Kind: IdentityCredentialOAuth,
			Provider: IdentityProviderGoogle, Identifier: "globally-unique-google-subject",
			VerifiedEmail: "subject-attacker@example.cn",
			TenantID:      attackerOrgID, ProjectID: attackerProjectID,
		})
		attackerCommand := authorizeIdentityCredentialLink(
			t, instance, attacker.AccountID, attackerSessionID, attackerSessionDigest,
			attackerOrgID, attackerProjectID, attackerProof, "subject-attacker-link", h.now,
		)
		for attempt := 0; attempt < 2; attempt++ {
			_, linkErr := instance.credentialLinkService.Complete(
				context.Background(), attackerCommand,
			)
			var domain IdentityDomainError
			if !errors.As(linkErr, &domain) ||
				domain.Code != "identity_credential_link_conflict" {
				t.Fatalf("cross-account subject conflict attempt %d returned %v", attempt+1, linkErr)
			}
			if strings.Contains(linkErr.Error(), "identity_credential_link_conflict") {
				t.Fatalf("cross-account subject conflict leaked PostgreSQL detail: %v", linkErr)
			}
		}

		var ownerCredentials, attackerCredentials int
		var proofUnconsumed, ticketUnconsumed, stepUpUnconsumed bool
		var attackerEvents int
		if err := instance.adminDB.QueryRow(`
SELECT
  (SELECT count(*) FROM identity_credentials WHERE principal_id=$1::uuid),
  (SELECT count(*) FROM identity_credentials WHERE principal_id=$2::uuid),
  (SELECT consumed_at IS NULL FROM identity_lifecycle_receipts WHERE receipt_digest=$3),
  (SELECT consumed_at IS NULL FROM identity_security_mutation_tickets WHERE ticket_digest=$4),
  (SELECT consumed_at IS NULL FROM identity_security_receipts WHERE receipt_digest=$5),
  (SELECT count(*) FROM identity_audit_events
    WHERE principal_id=$2::uuid AND action='identity.credential.link.completed')
`, owner.AccountID, attacker.AccountID,
			instance.receipts.receiptDigest(attackerProof.ReceiptID),
			attackerCommand.MutationTicketID, attackerCommand.StepUpReceiptID).
			Scan(
				&ownerCredentials, &attackerCredentials,
				&proofUnconsumed, &ticketUnconsumed, &stepUpUnconsumed,
				&attackerEvents,
			); err != nil {
			t.Fatal(err)
		}
		if ownerCredentials != 2 || attackerCredentials != 1 ||
			!proofUnconsumed || !ticketUnconsumed || !stepUpUnconsumed ||
			attackerEvents != 0 {
			t.Fatalf(
				"cross-account rollback owner_credentials=%d attacker_credentials=%d proof_unconsumed=%t ticket_unconsumed=%t step_up_unconsumed=%t events=%d",
				ownerCredentials, attackerCredentials,
				proofUnconsumed, ticketUnconsumed, stepUpUnconsumed,
				attackerEvents,
			)
		}
	})

	t.Run("canonical email conflict rolls back credential and authorization", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		instance := h.newInstance(t, []byte("email-conflict-key-0123456789012345"), "v1", nil)
		register := func(email, displayName string) IdentityAccountDTO {
			t.Helper()
			proof := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
				Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
				Provider: IdentityProviderLocal, Identifier: email,
				VerifiedEmail: email, DisplayName: displayName,
			})
			account, err := instance.service.CompleteRegistration(completionFor(proof))
			if err != nil {
				t.Fatalf("register %s: %v", email, err)
			}
			return account
		}
		owner := register("canonical-email-owner@example.cn", "Canonical Email Owner")
		target := register("canonical-email-target@example.cn", "Canonical Email Target")

		orgID := "60000000-0000-4000-8000-000000000001"
		workspaceID := "60000000-0000-4000-8000-000000000002"
		projectID := "60000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t, instance, target.AccountID, orgID, workspaceID, projectID, h.now,
		)
		sessionID, sessionDigest := issueScopedIdentitySession(
			t, instance, target.AccountID, target.Credentials[0].CredentialID,
			orgID, projectID, h.now,
		)
		proof := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation: IdentityOperationCredentialLink, Kind: IdentityCredentialOAuth,
			Provider: IdentityProviderGitHub, Identifier: "distinct-github-subject",
			VerifiedEmail: "canonical-email-owner@example.cn",
			TenantID:      orgID, ProjectID: projectID,
		})
		command := authorizeIdentityCredentialLink(
			t, instance, target.AccountID, sessionID, sessionDigest,
			orgID, projectID, proof, "canonical-email-conflict", h.now,
		)
		for attempt := 0; attempt < 2; attempt++ {
			_, linkErr := instance.credentialLinkService.Complete(
				context.Background(), command,
			)
			var domain IdentityDomainError
			if !errors.As(linkErr, &domain) ||
				domain.Code != "identity_credential_link_conflict" {
				t.Fatalf("canonical email conflict attempt %d returned %v", attempt+1, linkErr)
			}
			if strings.Contains(linkErr.Error(), "canonical_email_conflict") {
				t.Fatalf("canonical email conflict leaked PostgreSQL detail: %v", linkErr)
			}
		}

		var ownerCredentials, targetCredentials, emailOwners int
		var proofUnconsumed, ticketUnconsumed, stepUpUnconsumed bool
		var targetEvents int
		if err := instance.adminDB.QueryRow(`
SELECT
  (SELECT count(*) FROM identity_credentials WHERE principal_id=$1::uuid),
  (SELECT count(*) FROM identity_credentials WHERE principal_id=$2::uuid),
  (SELECT count(*) FROM identity_account_emails
    WHERE principal_id IN ($1::uuid,$2::uuid)),
  (SELECT consumed_at IS NULL FROM identity_lifecycle_receipts WHERE receipt_digest=$3),
  (SELECT consumed_at IS NULL FROM identity_security_mutation_tickets WHERE ticket_digest=$4),
  (SELECT consumed_at IS NULL FROM identity_security_receipts WHERE receipt_digest=$5),
  (SELECT count(*) FROM identity_audit_events
    WHERE principal_id=$2::uuid AND action='identity.credential.link.completed')
`, owner.AccountID, target.AccountID,
			instance.receipts.receiptDigest(proof.ReceiptID),
			command.MutationTicketID, command.StepUpReceiptID).
			Scan(
				&ownerCredentials, &targetCredentials, &emailOwners,
				&proofUnconsumed, &ticketUnconsumed, &stepUpUnconsumed,
				&targetEvents,
			); err != nil {
			t.Fatal(err)
		}
		if ownerCredentials != 1 || targetCredentials != 1 || emailOwners != 2 ||
			!proofUnconsumed || !ticketUnconsumed || !stepUpUnconsumed ||
			targetEvents != 0 {
			t.Fatalf(
				"canonical email rollback owner_credentials=%d target_credentials=%d email_owners=%d proof_unconsumed=%t ticket_unconsumed=%t step_up_unconsumed=%t events=%d",
				ownerCredentials, targetCredentials, emailOwners,
				proofUnconsumed, ticketUnconsumed, stepUpUnconsumed,
				targetEvents,
			)
		}
	})

	t.Run("foreign project scope is rejected with complete rollback", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		instance := h.newInstance(t, []byte("foreign-scope-key-01234567890123456"), "v1", nil)
		register := func(email, displayName string) IdentityAccountDTO {
			t.Helper()
			proof := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
				Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
				Provider: IdentityProviderLocal, Identifier: email,
				VerifiedEmail: email, DisplayName: displayName,
			})
			account, err := instance.service.CompleteRegistration(completionFor(proof))
			if err != nil {
				t.Fatalf("register %s: %v", email, err)
			}
			return account
		}
		target := register("scope-target@example.cn", "Scope Target")
		foreign := register("scope-foreign@example.cn", "Scope Foreign")

		targetOrgID := "70000000-0000-4000-8000-000000000001"
		targetWorkspaceID := "70000000-0000-4000-8000-000000000002"
		targetProjectID := "70000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t, instance, target.AccountID,
			targetOrgID, targetWorkspaceID, targetProjectID, h.now,
		)
		targetSessionID, targetSessionDigest := issueScopedIdentitySession(
			t, instance, target.AccountID, target.Credentials[0].CredentialID,
			targetOrgID, targetProjectID, h.now,
		)

		foreignOrgID := "80000000-0000-4000-8000-000000000001"
		foreignWorkspaceID := "80000000-0000-4000-8000-000000000002"
		foreignProjectID := "80000000-0000-4000-8000-000000000003"
		establishIdentityProjectScope(
			t, instance, foreign.AccountID,
			foreignOrgID, foreignWorkspaceID, foreignProjectID, h.now,
		)
		proof := issueLifecycleProof(t, instance.service, TrustedIdentityProof{
			Operation: IdentityOperationCredentialLink, Kind: IdentityCredentialOAuth,
			Provider: IdentityProviderGitHub, Identifier: "foreign-scope-github-subject",
			VerifiedEmail: "scope-target@example.cn",
			TenantID:      foreignOrgID, ProjectID: foreignProjectID,
		})
		command := authorizeIdentityCredentialLink(
			t, instance, target.AccountID, targetSessionID, targetSessionDigest,
			foreignOrgID, foreignProjectID, proof, "foreign-project-scope", h.now,
		)
		for attempt := 0; attempt < 2; attempt++ {
			_, linkErr := instance.credentialLinkService.Complete(
				context.Background(), command,
			)
			var domain IdentityDomainError
			if !errors.As(linkErr, &domain) ||
				domain.Code != "identity_credential_link_rejected" {
				t.Fatalf("foreign project scope attempt %d returned %v", attempt+1, linkErr)
			}
			if strings.Contains(linkErr.Error(), "identity session scope") {
				t.Fatalf("foreign project scope leaked PostgreSQL detail: %v", linkErr)
			}
		}

		var targetCredentials, foreignCredentials int
		var proofUnconsumed, ticketUnconsumed, stepUpUnconsumed bool
		var targetEvents int
		if err := instance.adminDB.QueryRow(`
SELECT
  (SELECT count(*) FROM identity_credentials WHERE principal_id=$1::uuid),
  (SELECT count(*) FROM identity_credentials WHERE principal_id=$2::uuid),
  (SELECT consumed_at IS NULL FROM identity_lifecycle_receipts WHERE receipt_digest=$3),
  (SELECT consumed_at IS NULL FROM identity_security_mutation_tickets WHERE ticket_digest=$4),
  (SELECT consumed_at IS NULL FROM identity_security_receipts WHERE receipt_digest=$5),
  (SELECT count(*) FROM identity_audit_events
    WHERE principal_id=$1::uuid AND action='identity.credential.link.completed')
`, target.AccountID, foreign.AccountID,
			instance.receipts.receiptDigest(proof.ReceiptID),
			command.MutationTicketID, command.StepUpReceiptID).
			Scan(
				&targetCredentials, &foreignCredentials,
				&proofUnconsumed, &ticketUnconsumed, &stepUpUnconsumed,
				&targetEvents,
			); err != nil {
			t.Fatal(err)
		}
		if targetCredentials != 1 || foreignCredentials != 1 ||
			!proofUnconsumed || !ticketUnconsumed || !stepUpUnconsumed ||
			targetEvents != 0 {
			t.Fatalf(
				"foreign scope rollback target_credentials=%d foreign_credentials=%d proof_unconsumed=%t ticket_unconsumed=%t step_up_unconsumed=%t events=%d",
				targetCredentials, foreignCredentials,
				proofUnconsumed, ticketUnconsumed, stepUpUnconsumed,
				targetEvents,
			)
		}
	})

	t.Run("receipt key rotation and tamper fail closed", func(t *testing.T) {
		h := newPostgresLifecycleHarness(t, adminDSN)
		oldKey := []byte("old-lifecycle-key-01234567890123456")
		newKey := []byte("new-lifecycle-key-01234567890123456")
		old := h.newInstance(t, oldKey, "old", nil)
		receipt := issueLifecycleProof(t, old.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "rotated@example.cn",
		})
		rotated := h.newInstance(t, newKey, "new", []IdentityLifecycleEncryptionKey{{Version: "old", Key: oldKey}})
		if _, err := rotated.service.CompleteRegistration(completionFor(receipt)); err != nil {
			t.Fatalf("previous key could not complete receipt after restart: %v", err)
		}

		missingReceipt := issueLifecycleProof(t, old.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "retired@example.cn",
		})
		withoutOld := h.newInstance(t, newKey, "new", nil)
		if _, err := withoutOld.service.CompleteRegistration(completionFor(missingReceipt)); !errors.Is(err, ErrIdentityProofReceiptNotFound) {
			t.Fatalf("missing retired key returned %v", err)
		}
		if _, err := rotated.service.CompleteRegistration(completionFor(missingReceipt)); err != nil {
			t.Fatalf("missing-key failure consumed receipt: %v", err)
		}

		for _, column := range []string{"proof_ciphertext", "proof_nonce", "tenant_scope", "proof_key_version"} {
			t.Run(column, func(t *testing.T) {
				proof := TrustedIdentityProof{
					Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
					Provider: IdentityProviderLocal, Identifier: "tamper-" + column + "@example.cn",
				}
				item := issueLifecycleProof(t, rotated.service, proof)
				digest := rotated.receipts.receiptDigest(item.ReceiptID)
				switch column {
				case "proof_ciphertext":
					mustExecArgs(t, rotated.adminDB, `UPDATE identity_lifecycle_receipts SET proof_ciphertext=set_byte(proof_ciphertext,0,get_byte(proof_ciphertext,0)#1) WHERE receipt_digest=$1`, digest)
				case "proof_nonce":
					mustExecArgs(t, rotated.adminDB, `UPDATE identity_lifecycle_receipts SET proof_nonce=set_byte(proof_nonce,0,get_byte(proof_nonce,0)#1) WHERE receipt_digest=$1`, digest)
				case "tenant_scope":
					mustExecArgs(t, rotated.adminDB, `UPDATE identity_lifecycle_receipts SET tenant_scope='tampered' WHERE receipt_digest=$1`, digest)
				case "proof_key_version":
					mustExecArgs(t, rotated.adminDB, `UPDATE identity_lifecycle_receipts SET proof_key_version='missing' WHERE receipt_digest=$1`, digest)
				}
				_, err := rotated.service.CompleteRegistration(completionFor(item))
				if err == nil {
					t.Fatal("tampered receipt was accepted")
				}
				var consumedAt sql.NullTime
				if scanErr := rotated.adminDB.QueryRow(`SELECT consumed_at FROM identity_lifecycle_receipts WHERE receipt_digest=$1`, digest).Scan(&consumedAt); scanErr != nil {
					t.Fatal(scanErr)
				}
				if consumedAt.Valid {
					t.Fatal("tampering consumed receipt")
				}
			})
		}

		wrongReceipt := issueLifecycleProof(t, rotated.service, TrustedIdentityProof{
			Operation: IdentityOperationRegistration, Kind: IdentityCredentialEmail,
			Provider: IdentityProviderLocal, Identifier: "wrong-key@example.cn",
		})
		wrong := h.newInstance(t, []byte("bad-lifecycle-key-01234567890123456"), "new", nil)
		if _, err := wrong.service.CompleteRegistration(completionFor(wrongReceipt)); err == nil {
			t.Fatal("wrong key material opened receipt")
		}
		if _, err := rotated.service.CompleteRegistration(completionFor(wrongReceipt)); err != nil {
			t.Fatalf("wrong-key failure consumed receipt: %v", err)
		}
	})
}

func newPostgresLifecycleHarness(t *testing.T, adminDSN string) *postgresLifecycleHarness {
	t.Helper()
	admin, err := sql.Open("postgres", adminDSN)
	if err != nil {
		t.Fatal(err)
	}
	defer admin.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := admin.PingContext(ctx); err != nil {
		t.Fatalf("connect identity lifecycle PostgreSQL: %v", err)
	}
	if _, err := admin.ExecContext(ctx, `
DO $$
BEGIN
  CREATE ROLE a1_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;
DO $$
BEGIN
  CREATE ROLE a1_security_ticket_issuer NOLOGIN NOSUPERUSER NOCREATEDB
    NOCREATEROLE NOINHERIT NOBYPASSRLS;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;
ALTER ROLE a1_security_ticket_issuer NOLOGIN NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOINHERIT NOBYPASSRLS;
`); err != nil {
		t.Fatalf("ensure migration runtime role: %v", err)
	}
	dbName := fmt.Sprintf("ashr_identity_lifecycle_%d", time.Now().UnixNano())
	runtimeRole := fmt.Sprintf("a1_lifecycle_test_%d", time.Now().UnixNano())
	runtimePassword := fmt.Sprintf("runtime-%d-test-only", time.Now().UnixNano())
	issuerRole := fmt.Sprintf("a1_security_issuer_test_%d", time.Now().UnixNano())
	issuerPassword := fmt.Sprintf("issuer-%d-test-only", time.Now().UnixNano())
	if _, err := admin.ExecContext(ctx, `CREATE ROLE `+quotePostgresIdentifier(runtimeRole)+
		` LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD `+
		quotePostgresLiteral(runtimePassword)); err != nil {
		t.Fatalf("create disposable runtime role: %v", err)
	}
	if _, err := admin.ExecContext(ctx, `CREATE ROLE `+quotePostgresIdentifier(issuerRole)+
		` LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD `+
		quotePostgresLiteral(issuerPassword)); err != nil {
		t.Fatalf("create disposable issuer login role: %v", err)
	}
	if _, err := admin.ExecContext(ctx, `GRANT a1_security_ticket_issuer TO `+
		quotePostgresIdentifier(issuerRole)); err != nil {
		t.Fatalf("grant issuer capability role: %v", err)
	}
	if _, err := admin.ExecContext(ctx, `CREATE DATABASE `+quotePostgresIdentifier(dbName)); err != nil {
		t.Fatalf("create disposable database: %v", err)
	}
	dsn := replacePostgresDatabase(adminDSN, dbName)
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatal(err)
	}
	applyIdentityLifecycleMigrations(t, db)
	if _, err := db.Exec(`GRANT CONNECT ON DATABASE ` + quotePostgresIdentifier(dbName) + ` TO ` +
		quotePostgresIdentifier(runtimeRole)); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`GRANT USAGE ON SCHEMA public TO ` + quotePostgresIdentifier(runtimeRole)); err != nil {
		t.Fatal(err)
	}
	for _, signature := range []string{
		"a1_issue_identity_lifecycle_receipt(TEXT,TEXT,TEXT,TEXT,TEXT,BYTEA,TEXT,TEXT,BYTEA,TIMESTAMPTZ)",
		"a1_identity_lifecycle_lookup_retirement_readiness(TEXT,TEXT[],TIMESTAMPTZ)",
		"a1_purge_identity_credential_link_replays(TIMESTAMPTZ,INTEGER,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ)",
		"a1_lock_identity_lifecycle_receipt(TEXT[])",
		"a1_consume_identity_lifecycle_receipt(TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ)",
		"a1_register_identity_lifecycle_credential(TEXT,TEXT,TEXT[],TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ)",
		"a1_authenticate_identity_lifecycle_credential(TEXT,TEXT[],TIMESTAMPTZ)",
		"a1_project_identity_lifecycle_account(UUID)",
		"a1_issue_identity_session(UUID,UUID,TEXT,TEXT,TIMESTAMPTZ,UUID,UUID,TEXT,TEXT,JSONB)",
		"a1_resolve_identity_security_mutation_ticket(TEXT,TEXT,TEXT,UUID,TIMESTAMPTZ)",
		"a1_execute_identity_security_mutation(TEXT,TEXT,TEXT,UUID)",
		"a1_project_account_security(UUID)",
		"a1_bind_verified_identity_credential_authorized(UUID,UUID,TEXT,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB)",
		"a1_issue_identity_verification_challenge_with_delivery(UUID,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,INTEGER,INTEGER,TEXT,TEXT,JSONB)",
		"a1_verify_identity_verification_attempt(UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB)",
		"a1_register_with_verified_identity_with_refresh(UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,TEXT,TEXT,JSONB)",
		"a1_login_with_verified_identity_with_refresh_result(UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,TEXT,JSONB)",
		"a1_recover_verified_identity_with_refresh_result(UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,TEXT,JSONB)",
		"a1_authenticate_identity_session_digest(TEXT)",
		"a1_rotate_identity_session_refresh_from_digest(UUID,UUID,TEXT,TEXT,TEXT,TIMESTAMPTZ,TEXT,TEXT,JSONB)",
		"a1_lock_identity_credential_link_receipt(TEXT[])",
		"a1_complete_identity_credential_link(UUID,UUID,TEXT,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,JSONB)",
		"a1_complete_oauth_first_login_with_refresh(UUID,UUID,TEXT,TEXT[],TEXT[],TEXT,TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ,TEXT,TEXT,TEXT,JSONB)",
		"a1_create_oauth_runtime_transaction(UUID,UUID,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ,TIMESTAMPTZ)",
		"a1_consume_oauth_runtime_transaction(TEXT,TEXT,TIMESTAMPTZ)",
	} {
		if _, err := db.Exec(`GRANT EXECUTE ON FUNCTION ` + signature + ` TO ` +
			quotePostgresIdentifier(runtimeRole)); err != nil {
			t.Fatalf("grant lifecycle function %s: %v", signature, err)
		}
	}
	runtimeDSN := replacePostgresCredentials(dsn, runtimeRole, runtimePassword)
	runtimeDSN = replacePostgresPeerSocketHost(runtimeDSN)
	issuerDSN := replacePostgresCredentials(dsn, issuerRole, issuerPassword)
	issuerDSN = replacePostgresPeerSocketHost(issuerDSN)
	issuerDSN = addPostgresConnectionOption(
		issuerDSN,
		"-c role=a1_security_ticket_issuer",
	)
	var databaseNow time.Time
	if err := db.QueryRowContext(ctx, `SELECT clock_timestamp()`).Scan(&databaseNow); err != nil {
		t.Fatalf("read disposable database clock: %v", err)
	}
	t.Cleanup(func() {
		_ = db.Close()
		cleanup, openErr := sql.Open("postgres", adminDSN)
		if openErr != nil {
			t.Logf("open cleanup database: %v", openErr)
			return
		}
		defer cleanup.Close()
		_, _ = cleanup.Exec(`SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=$1`, dbName)
		if _, dropErr := cleanup.Exec(`DROP DATABASE IF EXISTS ` + quotePostgresIdentifier(dbName)); dropErr != nil {
			t.Logf("drop disposable database: %v", dropErr)
		}
		if _, dropErr := cleanup.Exec(`DROP ROLE IF EXISTS ` + quotePostgresIdentifier(runtimeRole)); dropErr != nil {
			t.Logf("drop disposable runtime role: %v", dropErr)
		}
		if _, dropErr := cleanup.Exec(`DROP ROLE IF EXISTS ` + quotePostgresIdentifier(issuerRole)); dropErr != nil {
			t.Logf("drop disposable issuer role: %v", dropErr)
		}
	})
	return &postgresLifecycleHarness{
		adminDSN: adminDSN, dbName: dbName, adminDB: db,
		runtimeDSN: runtimeDSN, runtimeRole: runtimeRole,
		issuerDSN: issuerDSN, issuerRole: issuerRole,
		now: databaseNow.UTC(),
	}
}

func (h *postgresLifecycleHarness) newInstance(
	t *testing.T,
	lifecycleKey []byte,
	keyVersion string,
	previous []IdentityLifecycleEncryptionKey,
) *postgresLifecycleInstance {
	return h.newInstanceWithLifecycleKeys(
		t,
		lifecycleKey,
		keyVersion,
		previous,
		nil,
		"",
		nil,
	)
}

func (h *postgresLifecycleHarness) newInstanceWithLifecycleKeys(
	t *testing.T,
	lifecycleKey []byte,
	keyVersion string,
	previous []IdentityLifecycleEncryptionKey,
	lookupKey []byte,
	lookupKeyVersion string,
	previousLookup []IdentityLifecycleLookupKey,
) *postgresLifecycleInstance {
	t.Helper()
	db, err := sql.Open("postgres", h.runtimeDSN)
	if err != nil {
		t.Fatal(err)
	}
	db.SetMaxOpenConns(16)
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, Now: func() time.Time { return h.now },
		SessionKey:                         []byte("session-hmac-key-012345678901234567"),
		SessionKeyVersion:                  "integration",
		LifecycleReceiptKey:                lifecycleKey,
		LifecycleReceiptKeyVersion:         keyVersion,
		PreviousLifecycleReceiptKeys:       previous,
		LifecycleReceiptLookupKey:          lookupKey,
		LifecycleReceiptLookupKeyVersion:   lookupKeyVersion,
		PreviousLifecycleReceiptLookupKeys: previousLookup,
		SQLTimeout:                         10 * time.Second, StatementTimeout: 9 * time.Second, LockTimeout: 8 * time.Second,
	})
	if err != nil {
		_ = db.Close()
		t.Fatal(err)
	}
	if err := store.Ready(context.Background()); err != nil {
		_ = store.Close()
		t.Fatalf("production identity readiness: %v", err)
	}
	receiptStore, err := store.NewIdentityLifecycleReceiptStore()
	if err != nil {
		_ = store.Close()
		t.Fatal(err)
	}
	receipts := receiptStore.(*postgresIdentityLifecycleReceiptStore)
	coordinator, err := NewPostgresIdentityLifecycleTransactionCoordinator(store, receipts)
	if err != nil {
		_ = store.Close()
		t.Fatal(err)
	}
	identity, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{
		Now:            func() time.Time { return h.now },
		FingerprintKey: []byte("identity-fingerprint-012345678901234"),
	})
	if err != nil {
		_ = store.Close()
		t.Fatal(err)
	}
	service, err := NewIdentityLifecycleService(identity, IdentityLifecycleOptions{
		Now: func() time.Time { return h.now }, ReceiptTTL: 5 * time.Minute,
		ReceiptStore: receipts, Coordinator: coordinator,
		GitHubEnabled: true, GoogleEnabled: true, Environment: "test",
	})
	if err != nil {
		_ = store.Close()
		t.Fatal(err)
	}
	linkCoordinator, err := NewPostgresIdentityCredentialLinkCoordinator(store, receipts)
	if err != nil {
		_ = store.Close()
		t.Fatal(err)
	}
	credentialLinkService, err := NewIdentityCredentialLinkService(
		linkCoordinator, func() time.Time { return h.now },
	)
	if err != nil {
		_ = store.Close()
		t.Fatal(err)
	}
	instance := &postgresLifecycleInstance{
		db: db, adminDB: h.adminDB, store: store, receipts: receipts, service: service,
		credentialLinkService: credentialLinkService,
	}
	t.Cleanup(func() { _ = instance.store.Close() })
	return instance
}

func applyIdentityLifecycleMigrations(t *testing.T, db *sql.DB) {
	t.Helper()
	_, currentFile, _, _ := runtime.Caller(0)
	migrationsDir := filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", "..", "..", "services", "api", "migrations"))
	entries, err := filepath.Glob(filepath.Join(migrationsDir, "*.sql"))
	if err != nil {
		t.Fatal(err)
	}
	sort.Strings(entries)
	applied := 0
	for _, path := range entries {
		base := filepath.Base(path)
		if len(base) < 3 || base[:3] < "001" || base[:3] > "028" {
			continue
		}
		sqlBytes, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := db.Exec(string(sqlBytes)); err != nil {
			t.Fatalf("apply migration %s: %v", base, err)
		}
		applied++
	}
	if applied != 28 {
		t.Fatalf("expected migrations 001-028, applied %d from %s", applied, migrationsDir)
	}
}

func replacePostgresDatabase(dsn, database string) string {
	question := strings.IndexByte(dsn, '?')
	suffix := ""
	if question >= 0 {
		suffix = dsn[question:]
		dsn = dsn[:question]
	}
	slash := strings.LastIndexByte(dsn, '/')
	if slash < 0 {
		return dsn
	}
	return dsn[:slash+1] + database + suffix
}

func replacePostgresCredentials(dsn, username, password string) string {
	parsed, err := url.Parse(dsn)
	if err != nil || parsed.Scheme == "" {
		return dsn
	}
	parsed.User = url.UserPassword(username, password)
	return parsed.String()
}

func replacePostgresPeerSocketHost(dsn string) string {
	parsed, err := url.Parse(dsn)
	if err != nil || parsed.Scheme == "" {
		return dsn
	}
	query := parsed.Query()
	if strings.HasPrefix(query.Get("host"), "/") {
		query.Set("host", "127.0.0.1")
		parsed.RawQuery = query.Encode()
	}
	return parsed.String()
}

func addPostgresConnectionOption(dsn string, option string) string {
	parsed, err := url.Parse(dsn)
	if err != nil || parsed.Scheme == "" {
		return dsn
	}
	query := parsed.Query()
	query.Set("options", option)
	parsed.RawQuery = query.Encode()
	return parsed.String()
}

func quotePostgresIdentifier(value string) string {
	return `"` + strings.ReplaceAll(value, `"`, `""`) + `"`
}

func quotePostgresLiteral(value string) string {
	return `'` + strings.ReplaceAll(value, `'`, `''`) + `'`
}

func mustExec(t *testing.T, db *sql.DB, statement string) {
	t.Helper()
	if _, err := db.Exec(statement); err != nil {
		t.Fatal(err)
	}
}

func mustExecArgs(t *testing.T, db *sql.DB, statement string, args ...any) {
	t.Helper()
	if _, err := db.Exec(statement, args...); err != nil {
		t.Fatal(err)
	}
}

func assertIdentityCounts(t *testing.T, db *sql.DB, principals, credentials int) {
	t.Helper()
	var actualPrincipals, actualCredentials int
	if err := db.QueryRow(`SELECT count(*) FROM identity_principals`).Scan(&actualPrincipals); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(`SELECT count(*) FROM identity_credentials`).Scan(&actualCredentials); err != nil {
		t.Fatal(err)
	}
	if actualPrincipals != principals || actualCredentials != credentials {
		t.Fatalf("identity counts=%d/%d want=%d/%d", actualPrincipals, actualCredentials, principals, credentials)
	}
}

func assertPublicIdentityJSON(t *testing.T, value any) {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	lower := strings.ToLower(string(encoded))
	for _, forbidden := range []string{
		"subject_digest", "subject_id", "verified_email", "raw_email",
		"secret_ref", "password_secret", "receipt_id", "receipt_digest",
		"google-owner-subject", "owner@example",
	} {
		if strings.Contains(lower, forbidden) {
			t.Fatalf("public identity DTO leaked %q: %s", forbidden, encoded)
		}
	}
}

func createIdentityVerificationProjectScope(
	t *testing.T,
	db *sql.DB,
	organizationID string,
	workspaceID string,
	projectID string,
	slugPrefix string,
) {
	t.Helper()
	mustExecArgs(t, db, `
INSERT INTO organizations(id,slug,display_name)
VALUES ($1::uuid,$2,'Identity Verification Organization')
`, organizationID, slugPrefix+"-organization")
	mustExecArgs(t, db, `
INSERT INTO workspaces(id,organization_id,slug,display_name)
VALUES ($1::uuid,$2::uuid,$3,'Identity Verification Workspace')
`, workspaceID, organizationID, slugPrefix+"-workspace")
	mustExecArgs(t, db, `
INSERT INTO projects(id,organization_id,workspace_id,slug,display_name)
VALUES ($1::uuid,$2::uuid,$3::uuid,$4,'Identity Verification Project')
`, projectID, organizationID, workspaceID, slugPrefix+"-project")
}

func establishIdentityProjectScope(
	t *testing.T,
	instance *postgresLifecycleInstance,
	principalID string,
	organizationID string,
	workspaceID string,
	projectID string,
	now time.Time,
) {
	t.Helper()
	scopeSuffix := strings.ToLower(strings.ReplaceAll(organizationID, "-", ""))
	if len(scopeSuffix) > 8 {
		scopeSuffix = scopeSuffix[:8]
	}
	mustExecArgs(t, instance.adminDB, `
INSERT INTO organizations(id,slug,display_name)
VALUES ($1::uuid,$2,'Credential Link Org')
`, organizationID, "credential-link-org-"+scopeSuffix)
	mustExecArgs(t, instance.adminDB, `
INSERT INTO workspaces(id,organization_id,slug,display_name)
VALUES ($1::uuid,$2::uuid,$3,'Credential Link Workspace')
`, workspaceID, organizationID, "credential-link-workspace-"+scopeSuffix)
	mustExecArgs(t, instance.adminDB, `
INSERT INTO projects(id,organization_id,workspace_id,slug,display_name)
VALUES ($1::uuid,$2::uuid,$3::uuid,$4,'Credential Link Project')
`, projectID, organizationID, workspaceID, "credential-link-project-"+scopeSuffix)
	var organizationMembershipID string
	if err := instance.adminDB.QueryRow(`
INSERT INTO identity_organization_memberships(
  organization_id,principal_id,role,status,activated_at
) VALUES ($1::uuid,$2::uuid,'owner','active',$3)
RETURNING id::text
`, organizationID, principalID, now).Scan(&organizationMembershipID); err != nil {
		t.Fatal(err)
	}
	mustExecArgs(t, instance.adminDB, `
INSERT INTO identity_project_memberships(
  organization_id,project_id,principal_id,organization_membership_id,
  role,status,activated_at
) VALUES ($1::uuid,$2::uuid,$3::uuid,$4::uuid,'admin','active',$5)
`, organizationID, projectID, principalID, organizationMembershipID, now)
}

func issueScopedIdentitySession(
	t *testing.T,
	instance *postgresLifecycleInstance,
	principalID string,
	credentialID string,
	organizationID string,
	projectID string,
	now time.Time,
) (string, string) {
	t.Helper()
	token, err := instance.store.sessionTokens.issue()
	if err != nil {
		t.Fatal(err)
	}
	rotationDigest, err := instance.store.sessionTokens.digestActive(
		"identity-credential-link-integration", principalID, token.digest,
	)
	if err != nil {
		t.Fatal(err)
	}
	requestDigest := instance.receipts.receiptDigest(
		"identity-credential-link-session:" + principalID,
	)
	var sessionID string
	if err := instance.db.QueryRow(`
SELECT id::text FROM a1_issue_identity_session(
  $1::uuid,$2::uuid,$3,$4,$5,$6::uuid,$7::uuid,'aal1',$8,
  '{"source":"identity_credential_link_integration"}'::jsonb
)
`, principalID, credentialID, token.digest, rotationDigest, now.Add(30*time.Minute),
		organizationID, projectID, requestDigest).Scan(&sessionID); err != nil {
		t.Fatalf("issue scoped identity session: %v", err)
	}
	return sessionID, token.digest
}

func authorizeIdentityCredentialLink(
	t *testing.T,
	instance *postgresLifecycleInstance,
	principalID string,
	sessionID string,
	sessionDigest string,
	organizationID string,
	projectID string,
	proof IdentityProofReceiptDTO,
	idempotencyKey string,
	now time.Time,
) IdentityCredentialLinkCommand {
	t.Helper()
	proofDigest := instance.receipts.receiptDigest(proof.ReceiptID)
	requestDigest := instance.receipts.receiptDigest(strings.Join([]string{
		"credential-link:request", principalID, principalID,
		sessionID, organizationID, projectID,
		string(proof.Provider), proofDigest,
	}, "\x00"))
	stepUpReceiptDigest := instance.receipts.receiptDigest(
		"credential-link:step-up:" + proof.ReceiptID,
	)
	mutationTicketDigest := instance.receipts.receiptDigest(
		"credential-link:ticket:" + proof.ReceiptID,
	)
	mustExecArgs(t, instance.adminDB, `
INSERT INTO identity_security_receipts(
  receipt_digest,principal_id,purpose,context_digest,expires_at
) VALUES ($1,$2::uuid,'credential_bind',$3,$4)
`, stepUpReceiptDigest, principalID, requestDigest, now.Add(10*time.Minute))
	var issued bool
	if err := instance.adminDB.QueryRow(`
SELECT a1_issue_identity_security_mutation_ticket(
  $1,$2,$3::uuid,$3::uuid,'credential_bind',$4,
  NULL,NULL,NULL,NULL,$5
)
`, mutationTicketDigest, stepUpReceiptDigest, principalID, requestDigest,
		now.Add(5*time.Minute)).Scan(&issued); err != nil {
		t.Fatalf("issue credential-bind mutation ticket: %v", err)
	}
	if !issued {
		t.Fatal("credential-bind mutation ticket was not issued")
	}
	return IdentityCredentialLinkCommand{
		AccountID: principalID, ActorID: principalID,
		SessionID: sessionID, SessionDigest: sessionDigest,
		Provider: proof.Provider, TenantID: organizationID, ProjectID: projectID,
		ProofReceiptID:   proof.ReceiptID,
		MutationTicketID: mutationTicketDigest, StepUpReceiptID: stepUpReceiptDigest,
		IdempotencyKey: idempotencyKey,
	}
}

func exerciseAuthoritativeSecurityLifecycle(
	t *testing.T,
	instance *postgresLifecycleInstance,
	principalID string,
	now time.Time,
) {
	t.Helper()
	issueTicket := func(
		operation string,
		label string,
		secretRef any,
		secretDigest any,
		recoveryBatchDigest any,
		recoveryCodeCount any,
	) IdentitySecurityMutationTicket {
		t.Helper()
		receiptDigest := instance.receipts.receiptDigest("security-receipt:" + label)
		contextDigest := instance.receipts.receiptDigest("security-context:" + label)
		ticketDigest := instance.receipts.receiptDigest("security-ticket:" + label)
		mustExecArgs(t, instance.adminDB, `
INSERT INTO identity_security_receipts(
  receipt_digest,principal_id,purpose,context_digest,expires_at
) VALUES ($1,$2::uuid,$3,$4,$5)
`, receiptDigest, principalID, operation, contextDigest, now.Add(10*time.Minute))
		var issued bool
		if err := instance.adminDB.QueryRow(`
SELECT a1_issue_identity_security_mutation_ticket(
  $1,$2,$3::uuid,$3::uuid,$4,$5,$6,$7,$8,$9,$10
)
`, ticketDigest, receiptDigest, principalID, operation, contextDigest,
			secretRef, secretDigest, recoveryBatchDigest, recoveryCodeCount,
			now.Add(5*time.Minute)).Scan(&issued); err != nil {
			t.Fatalf("issue %s security mutation ticket: %v", operation, err)
		}
		if !issued {
			t.Fatalf("issue %s security mutation ticket returned false", operation)
		}
		ticket, err := instance.store.ResolveIdentitySecurityMutationTicket(
			context.Background(), principalID,
			ticketDigest, receiptDigest, operation,
		)
		if err != nil {
			t.Fatalf("resolve %s security mutation ticket: %v", operation, err)
		}
		return ticket
	}

	mutate := func(
		operation string,
		idempotencyKey string,
		ticket IdentitySecurityMutationTicket,
	) IdentitySecurityHTTPMutationResultDTO {
		t.Helper()
		mutation := IdentitySecurityMutation{
			AccountID: principalID, ActorID: principalID, SessionID: "integration-session",
			Operation: operation, IdempotencyKey: idempotencyKey, Ticket: ticket,
		}
		result, err := instance.store.MutateIdentitySecurity(context.Background(), mutation)
		if err != nil {
			t.Fatalf("execute %s security mutation: %v", operation, err)
		}
		replay, err := instance.store.MutateIdentitySecurity(context.Background(), mutation)
		if err != nil {
			t.Fatalf("replay %s security mutation: %v", operation, err)
		}
		if replay != result {
			t.Fatalf("%s replay changed result: first=%#v replay=%#v", operation, result, replay)
		}
		conflict := mutation
		conflict.SessionID = "different-integration-session"
		if _, err := instance.store.MutateIdentitySecurity(context.Background(), conflict); !errors.Is(err, ErrIdentitySecurityRejected) {
			t.Fatalf("%s idempotency binding conflict returned %v", operation, err)
		}
		return result
	}

	passwordTicket := issueTicket(
		"password_enroll",
		"password-enroll",
		"vault://identity/password/integration",
		strings.Repeat("a", 64),
		nil,
		nil,
	)
	passwordResult := mutate(
		"password_enroll",
		"password-enroll",
		passwordTicket,
	)
	if passwordResult.PasswordStatus != "set" || !passwordResult.ReauthenticationRequired {
		t.Fatalf("password lifecycle returned %#v", passwordResult)
	}

	enrollTicket := issueTicket(
		"mfa_enroll",
		"totp-enroll",
		"vault://identity/totp/integration",
		strings.Repeat("b", 64),
		nil,
		nil,
	)
	enrollResult := mutate(
		"mfa_enroll",
		"totp-enroll",
		enrollTicket,
	)
	if enrollResult.TwoFactorStatus != "pending" || !enrollResult.ConfirmationRequired {
		t.Fatalf("TOTP enrollment returned %#v", enrollResult)
	}

	confirmTicket := issueTicket(
		"mfa_confirm",
		"totp-confirm",
		nil,
		nil,
		strings.Repeat("c", 64),
		10,
	)
	confirmResult := mutate(
		"mfa_confirm",
		"totp-confirm",
		confirmTicket,
	)
	if confirmResult.TwoFactorStatus != "enabled" ||
		confirmResult.RecoveryCodesRemaining != 10 ||
		!confirmResult.ReauthenticationRequired {
		t.Fatalf("TOTP confirmation returned %#v", confirmResult)
	}

	/*
		The production boundary deliberately receives only the public ticket
		projection. Secret refs, secret digests, context digests, and recovery
		material above are supplied only to PostgreSQL's trusted issuance
		authority and never re-enter the Go mutation path.
	*/
	_, err := instance.store.MutateIdentitySecurity(
		context.Background(),
		IdentitySecurityMutation{
			AccountID: principalID, ActorID: principalID, SessionID: "integration-session",
			Operation: "password_enroll", IdempotencyKey: "unissued-ticket",
			Ticket: IdentitySecurityMutationTicket{
				TicketID: strings.Repeat("d", 64), AccountID: principalID,
				Operation: "password_enroll", ReceiptDigest: strings.Repeat("e", 64),
				ExpiresAt: now.Add(5 * time.Minute),
			},
		},
	)
	if !errors.Is(err, ErrIdentitySecurityRejected) {
		t.Fatalf("unissued security mutation ticket returned %v", err)
	}

	posture, err := instance.store.GetIdentitySecurityPosture(context.Background(), principalID)
	if err != nil {
		t.Fatalf("project identity security posture through production store: %v", err)
	}
	if posture.PasswordStatus != "set" || posture.TwoFactorStatus != "enabled" ||
		!posture.TwoFactorOptional || !posture.TwoFactorRecommended ||
		posture.RecoveryCodesRemaining != 10 || posture.SecurityVersion < 3 {
		t.Fatalf("production identity security posture returned %#v", posture)
	}

	var consumedReceipts, revokedSessions int
	if err := instance.adminDB.QueryRow(`
SELECT
  (SELECT count(*) FROM identity_security_receipts
    WHERE principal_id=$1::uuid AND consumed_at IS NOT NULL),
  (SELECT count(*) FROM identity_sessions
    WHERE principal_id=$1::uuid AND status='revoked')
`, principalID).Scan(&consumedReceipts, &revokedSessions); err != nil {
		t.Fatalf("inspect security lifecycle effects: %v", err)
	}
	if consumedReceipts != 3 || revokedSessions < 1 {
		t.Fatalf("security lifecycle effects receipts=%d revoked_sessions=%d", consumedReceipts, revokedSessions)
	}
}

func assertIdentityAccountSecurityRLS(
	t *testing.T,
	harness *postgresLifecycleHarness,
	instance *postgresLifecycleInstance,
	principalID string,
	now time.Time,
) {
	t.Helper()
	otherPrincipalID := "20000000-0000-4000-8000-000000000001"
	mustExecArgs(t, instance.adminDB, `
INSERT INTO identity_principals(id,status,display_label)
VALUES ($1::uuid,'active','RLS Isolation Fixture')
`, otherPrincipalID)
	mustExecArgs(t, instance.adminDB, `
INSERT INTO identity_account_security(principal_id,updated_at)
VALUES ($1::uuid,$2)
`, otherPrincipalID, now)
	mustExec(t, instance.adminDB,
		`GRANT SELECT ON identity_account_security TO `+quotePostgresIdentifier(harness.runtimeRole))

	conn, err := instance.db.Conn(context.Background())
	if err != nil {
		t.Fatalf("open RLS runtime connection: %v", err)
	}
	defer conn.Close()
	tx, err := conn.BeginTx(context.Background(), nil)
	if err != nil {
		t.Fatalf("begin RLS runtime transaction: %v", err)
	}
	defer tx.Rollback()
	if _, err := tx.Exec(`SELECT set_config('app.a1_principal_id',$1,TRUE)`, principalID); err != nil {
		t.Fatalf("set RLS principal context: %v", err)
	}
	var visibleRows, foreignRows int
	if err := tx.QueryRow(`
SELECT count(*), count(*) FILTER (WHERE principal_id=$1::uuid)
FROM identity_account_security
`, otherPrincipalID).Scan(&visibleRows, &foreignRows); err != nil {
		t.Fatalf("query account security through RLS runtime role: %v", err)
	}
	if visibleRows != 1 || foreignRows != 0 {
		t.Fatalf("RLS exposed visible=%d foreign=%d account security rows", visibleRows, foreignRows)
	}
}
