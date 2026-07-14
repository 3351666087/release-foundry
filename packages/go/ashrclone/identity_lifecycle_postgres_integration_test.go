package ashrclone

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
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
	now         time.Time
}

type postgresLifecycleInstance struct {
	db       *sql.DB
	adminDB  *sql.DB
	store    *ProductionIdentityStore
	receipts *postgresIdentityLifecycleReceiptStore
	service  *IdentityLifecycleService
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
$$`); err != nil {
		t.Fatalf("ensure migration runtime role: %v", err)
	}
	dbName := fmt.Sprintf("ashr_identity_lifecycle_%d", time.Now().UnixNano())
	runtimeRole := fmt.Sprintf("a1_lifecycle_test_%d", time.Now().UnixNano())
	runtimePassword := fmt.Sprintf("runtime-%d-test-only", time.Now().UnixNano())
	if _, err := admin.ExecContext(ctx, `CREATE ROLE `+quotePostgresIdentifier(runtimeRole)+
		` LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD `+
		quotePostgresLiteral(runtimePassword)); err != nil {
		t.Fatalf("create disposable runtime role: %v", err)
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
		"a1_issue_identity_lifecycle_receipt(TEXT,TEXT,TEXT,TEXT,TEXT,BYTEA,TEXT,BYTEA,TIMESTAMPTZ)",
		"a1_lock_identity_lifecycle_receipt(TEXT[])",
		"a1_consume_identity_lifecycle_receipt(TEXT,TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ)",
		"a1_register_identity_lifecycle_credential(TEXT,TEXT,TEXT[],TEXT,TEXT,TEXT,TEXT,TIMESTAMPTZ)",
		"a1_authenticate_identity_lifecycle_credential(TEXT,TEXT[],TIMESTAMPTZ)",
		"a1_project_identity_lifecycle_account(UUID)",
		"a1_issue_identity_session(UUID,UUID,TEXT,TEXT,TIMESTAMPTZ,UUID,UUID,TEXT,TEXT,JSONB)",
		"a1_issue_identity_security_mutation_ticket(TEXT,TEXT,UUID,UUID,TEXT,TEXT,TEXT,TEXT,TEXT,INTEGER,TIMESTAMPTZ,TIMESTAMPTZ)",
		"a1_resolve_identity_security_mutation_ticket(TEXT,TEXT,TEXT,TIMESTAMPTZ)",
		"a1_execute_identity_security_mutation(TEXT,TEXT,TEXT,TIMESTAMPTZ)",
		"a1_project_account_security(UUID)",
	} {
		if _, err := db.Exec(`GRANT EXECUTE ON FUNCTION ` + signature + ` TO ` +
			quotePostgresIdentifier(runtimeRole)); err != nil {
			t.Fatalf("grant lifecycle function %s: %v", signature, err)
		}
	}
	runtimeDSN := replacePostgresCredentials(dsn, runtimeRole, runtimePassword)
	runtimeDSN = replacePostgresPeerSocketHost(runtimeDSN)
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
	})
	return &postgresLifecycleHarness{
		adminDSN: adminDSN, dbName: dbName, adminDB: db,
		runtimeDSN: runtimeDSN, runtimeRole: runtimeRole,
		now: databaseNow.UTC(),
	}
}

func (h *postgresLifecycleHarness) newInstance(
	t *testing.T,
	lifecycleKey []byte,
	keyVersion string,
	previous []IdentityLifecycleEncryptionKey,
) *postgresLifecycleInstance {
	t.Helper()
	db, err := sql.Open("postgres", h.runtimeDSN)
	if err != nil {
		t.Fatal(err)
	}
	db.SetMaxOpenConns(16)
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, Now: func() time.Time { return h.now },
		SessionKey:                   []byte("session-hmac-key-012345678901234567"),
		SessionKeyVersion:            "integration",
		LifecycleReceiptKey:          lifecycleKey,
		LifecycleReceiptKeyVersion:   keyVersion,
		PreviousLifecycleReceiptKeys: previous,
		SQLTimeout:                   10 * time.Second, StatementTimeout: 9 * time.Second, LockTimeout: 8 * time.Second,
	})
	if err != nil {
		_ = db.Close()
		t.Fatal(err)
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
	instance := &postgresLifecycleInstance{
		db: db, adminDB: h.adminDB, store: store, receipts: receipts, service: service,
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
		if len(base) < 3 || base[:3] < "001" || base[:3] > "018" {
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
	if applied != 18 {
		t.Fatalf("expected migrations 001-018, applied %d from %s", applied, migrationsDir)
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
		if err := instance.db.QueryRow(`
SELECT a1_issue_identity_security_mutation_ticket(
  $1,$2,$3::uuid,$3::uuid,$4,$5,$6,$7,$8,$9,$10,$11
)
`, ticketDigest, receiptDigest, principalID, operation, contextDigest,
			secretRef, secretDigest, recoveryBatchDigest, recoveryCodeCount,
			now.Add(5*time.Minute), now).Scan(&issued); err != nil {
			t.Fatalf("issue %s security mutation ticket: %v", operation, err)
		}
		if !issued {
			t.Fatalf("issue %s security mutation ticket returned false", operation)
		}
		ticket, err := instance.store.ResolveIdentitySecurityMutationTicket(
			context.Background(), ticketDigest, receiptDigest, operation,
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
