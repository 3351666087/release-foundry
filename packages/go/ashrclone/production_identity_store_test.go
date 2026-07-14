package ashrclone

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
)

func TestProductionIdentityStoreRequiresDBAndStrongSessionKey(t *testing.T) {
	if _, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{}); err == nil {
		t.Fatal("expected missing db to fail")
	}
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{DB: db, SessionKey: []byte("short")}); err == nil {
		t.Fatal("expected short key to fail")
	}
	key := bytes.Repeat([]byte{0x21}, 32)
	if _, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: key, SessionKeyVersion: "invalid version",
	}); err == nil {
		t.Fatal("expected invalid active key version to fail")
	}
	if _, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: key, SessionKeyVersion: "v2",
		PreviousSessionKeys: []IdentitySessionHMACKey{{Version: "v2", Key: key}},
	}); err == nil {
		t.Fatal("expected duplicate key version to fail")
	}
	if _, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: key, SessionKeyVersion: "v2", LegacySessionKeyVersion: "v1",
	}); err == nil {
		t.Fatal("expected missing legacy key version to fail")
	}
}

func TestProductionIdentityStoreProjectsCanonicalAccount(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: bytes.Repeat([]byte{0x61}, 32),
		SQLTimeout: time.Second, StatementTimeout: 800 * time.Millisecond, LockTimeout: 200 * time.Millisecond,
	})
	if err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 7, 12, 9, 0, 0, 0, time.UTC)
	projection := identityLifecycleAccountProjection{
		PrincipalID: "33333333-3333-4333-8333-333333333333",
		DisplayName: "Canonical PostgreSQL Account",
		Status:      "active",
		CreatedAt:   now,
		UpdatedAt:   now,
		Credentials: []identityLifecycleCredentialProjection{{
			CredentialID: "44444444-4444-4444-8444-444444444444",
			Provider:     string(IdentityProviderLocal), CredentialKind: string(IdentityCredentialEmail),
			Verified: true, CanLogin: true, LinkedAt: now,
		}},
		Memberships: []identityLifecycleMembershipProjection{{
			MembershipID: "55555555-5555-4555-8555-555555555555",
			TenantID:     "66666666-6666-4666-8666-666666666666",
			ProjectID:    "77777777-7777-4777-8777-777777777777",
			Role:         "owner", CreatedAt: now, UpdatedAt: now,
		}},
	}
	raw, err := json.Marshal(projection)
	if err != nil {
		t.Fatal(err)
	}
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").WithArgs("800ms", "200ms").
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery("SELECT a1_project_identity_lifecycle_account").
		WithArgs(projection.PrincipalID).
		WillReturnRows(sqlmock.NewRows([]string{"account"}).AddRow(string(raw)))
	mock.ExpectCommit()

	account, err := store.GetIdentityAccount(context.Background(), projection.PrincipalID)
	if err != nil {
		t.Fatal(err)
	}
	if account.AccountID != projection.PrincipalID || account.DisplayName != projection.DisplayName ||
		account.CredentialCount != 1 || account.MembershipCount != 1 {
		t.Fatalf("unexpected canonical account projection: %#v", account)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentityStoreAccountProjectionFailsClosed(t *testing.T) {
	const accountID = "33333333-3333-4333-8333-333333333333"
	for name, testCase := range map[string]struct {
		value any
		err   error
	}{
		"null":           {value: nil, err: ErrIdentityAccountNotFound},
		"malformed_json": {value: "{", err: nil},
	} {
		t.Run(name, func(t *testing.T) {
			db, mock, err := sqlmock.New()
			if err != nil {
				t.Fatal(err)
			}
			defer db.Close()
			store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
				DB: db, SessionKey: bytes.Repeat([]byte{0x62}, 32),
			})
			if err != nil {
				t.Fatal(err)
			}
			mock.ExpectBegin()
			mock.ExpectExec("SELECT set_config").
				WithArgs("5000ms", "2000ms").
				WillReturnResult(sqlmock.NewResult(0, 1))
			mock.ExpectQuery("SELECT a1_project_identity_lifecycle_account").
				WithArgs(accountID).
				WillReturnRows(sqlmock.NewRows([]string{"account"}).AddRow(testCase.value))
			mock.ExpectRollback()
			_, got := store.GetIdentityAccount(context.Background(), accountID)
			if testCase.err != nil {
				if !errors.Is(got, testCase.err) {
					t.Fatalf("expected %v, got %v", testCase.err, got)
				}
			} else if got == nil || strings.Contains(got.Error(), string(testCase.value.(string))) {
				t.Fatalf("malformed projection did not fail safely: %v", got)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestProductionIdentityStoreRejectsInvalidAccountIDBeforeQuery(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: bytes.Repeat([]byte{0x63}, 32),
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.GetIdentityAccount(context.Background(), "not-a-uuid"); !errors.Is(err, ErrIdentityAccountNotFound) {
		t.Fatalf("invalid UUID returned %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentityStoreAccountProjectionDatabaseFailures(t *testing.T) {
	const accountID = "33333333-3333-4333-8333-333333333333"
	databaseFailure := errors.New("database unavailable")
	tests := []struct {
		name   string
		expect func(sqlmock.Sqlmock)
	}{
		{
			name: "begin",
			expect: func(mock sqlmock.Sqlmock) {
				mock.ExpectBegin().WillReturnError(databaseFailure)
			},
		},
		{
			name: "timeout configuration",
			expect: func(mock sqlmock.Sqlmock) {
				mock.ExpectBegin()
				mock.ExpectExec("SELECT set_config").
					WithArgs("5000ms", "2000ms").
					WillReturnError(databaseFailure)
				mock.ExpectRollback()
			},
		},
		{
			name: "projection query",
			expect: func(mock sqlmock.Sqlmock) {
				mock.ExpectBegin()
				mock.ExpectExec("SELECT set_config").
					WithArgs("5000ms", "2000ms").
					WillReturnResult(sqlmock.NewResult(0, 1))
				mock.ExpectQuery("SELECT a1_project_identity_lifecycle_account").
					WithArgs(accountID).
					WillReturnError(databaseFailure)
				mock.ExpectRollback()
			},
		},
		{
			name: "commit",
			expect: func(mock sqlmock.Sqlmock) {
				projection := identityLifecycleAccountProjection{
					PrincipalID: accountID,
					DisplayName: "Canonical PostgreSQL Account",
					Status:      "active",
					CreatedAt:   time.Date(2026, 7, 12, 9, 0, 0, 0, time.UTC),
					UpdatedAt:   time.Date(2026, 7, 12, 9, 0, 0, 0, time.UTC),
				}
				raw, err := json.Marshal(projection)
				if err != nil {
					t.Fatal(err)
				}
				mock.ExpectBegin()
				mock.ExpectExec("SELECT set_config").
					WithArgs("5000ms", "2000ms").
					WillReturnResult(sqlmock.NewResult(0, 1))
				mock.ExpectQuery("SELECT a1_project_identity_lifecycle_account").
					WithArgs(accountID).
					WillReturnRows(sqlmock.NewRows([]string{"account"}).AddRow(string(raw)))
				mock.ExpectCommit().WillReturnError(databaseFailure)
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			db, mock, err := sqlmock.New()
			if err != nil {
				t.Fatal(err)
			}
			defer db.Close()
			store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
				DB: db, SessionKey: bytes.Repeat([]byte{0x64}, 32),
			})
			if err != nil {
				t.Fatal(err)
			}
			test.expect(mock)
			_, got := store.GetIdentityAccount(context.Background(), accountID)
			if got == nil || errors.Is(got, ErrIdentityAccountNotFound) ||
				errors.Is(got, ErrIdentityStoreUnavailable) {
				t.Fatalf("database failure was not preserved: %v", got)
			}
			if !errors.Is(got, databaseFailure) {
				t.Fatalf("database failure cause was lost: %v", got)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestProductionIdentityLifecycleReceiptStoreRequiresDedicatedKey(t *testing.T) {
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: bytes.Repeat([]byte{0x11}, 32),
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.NewIdentityLifecycleReceiptStore(); err == nil {
		t.Fatal("expected missing lifecycle receipt key to fail closed")
	}
	store.lifecycleKeys, err = newIdentityLifecycleKeyring(
		"v1", bytes.Repeat([]byte{0x22}, 32), nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	receiptStore, err := store.NewIdentityLifecycleReceiptStore()
	if err != nil {
		t.Fatal(err)
	}
	if !receiptStore.ProductionDurable() {
		t.Fatal("postgres lifecycle receipt store must identify as production durable")
	}
}

func TestPostgresLifecycleReceiptIssueUsesDigestAndEncryptedProof(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	keys, err := newIdentityLifecycleKeyring("v1", bytes.Repeat([]byte{0x42}, 32), nil)
	if err != nil {
		t.Fatal(err)
	}
	defer keys.close()
	store := &postgresIdentityLifecycleReceiptStore{
		db: db, keys: keys,
		sqlTimeout: time.Second, statementTimeout: time.Second, lockTimeout: 500 * time.Millisecond,
	}
	dto := IdentityProofReceiptDTO{
		ReceiptID: "ipr_raw-secret", Operation: IdentityOperationRegistration,
		Provider: IdentityProviderLocal, TenantID: "tenant-a", ProjectID: "project-a",
		ExpiresAt: time.Now().UTC().Add(time.Minute),
	}
	mock.ExpectExec("SELECT a1_issue_identity_lifecycle_receipt").
		WithArgs(
			store.receiptDigest(dto.ReceiptID), dto.Operation, dto.Provider,
			dto.TenantID, dto.ProjectID, sqlmock.AnyArg(), "v1", sqlmock.AnyArg(), dto.ExpiresAt,
		).
		WillReturnResult(sqlmock.NewResult(1, 1))
	if err := store.Issue(context.Background(), dto, TrustedIdentityProof{
		Operation: dto.Operation, Provider: dto.Provider, Kind: IdentityCredentialEmail,
		Identifier: "owner@example.cn", TenantID: dto.TenantID, ProjectID: dto.ProjectID,
	}); err != nil {
		t.Fatal(err)
	}
	if strings.Contains(store.receiptDigest(dto.ReceiptID), dto.ReceiptID) {
		t.Fatal("receipt digest exposed raw receipt")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresLifecycleReceiptConditionalConsumeHasOneWinnerShape(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	keys, err := newIdentityLifecycleKeyring("v1", bytes.Repeat([]byte{0x43}, 32), nil)
	if err != nil {
		t.Fatal(err)
	}
	defer keys.close()
	store := &postgresIdentityLifecycleReceiptStore{
		db: db, keys: keys,
		sqlTimeout: time.Second, statementTimeout: 900 * time.Millisecond, lockTimeout: 300 * time.Millisecond,
	}
	request := CompleteIdentityLifecycleRequest{
		ReceiptID: "ipr_once", Provider: IdentityProviderLocal,
		TenantID: "tenant-a", ProjectID: "project-a",
	}
	now := time.Now().UTC()
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").WithArgs("900ms", "300ms").
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery("SELECT receipt_digest, operation, provider, tenant_scope, project_scope, expires_at").
		WithArgs(sqlmock.AnyArg()).
		WillReturnRows(sqlmock.NewRows([]string{
			"receipt_digest", "operation", "provider", "tenant_scope", "project_scope", "expires_at",
			"consumed_at", "proof_nonce", "proof_key_version", "proof_ciphertext",
		}).AddRow(
			store.receiptDigest(request.ReceiptID), IdentityOperationRegistration,
			request.Provider, request.TenantID, request.ProjectID,
			now.Add(time.Minute), now, []byte("nonce-123456"), "v1", bytes.Repeat([]byte{0x44}, 32),
		))
	mock.ExpectRollback()
	_, err = store.Consume(context.Background(), request, IdentityOperationRegistration, now)
	if !errors.Is(err, ErrIdentityProofReceiptConsumed) {
		t.Fatalf("conditional loser returned %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentityStoreEnforcesPreviousKeyRetentionAndTimeoutOrdering(t *testing.T) {
	db, _, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	now := time.Date(2026, 7, 12, 0, 0, 0, 0, time.UTC)
	activeKey := bytes.Repeat([]byte{0x31}, 32)
	previousKey := bytes.Repeat([]byte{0x32}, 32)
	base := ProductionIdentityStoreOptions{
		DB: db, SessionKey: activeKey, SessionKeyVersion: "v2",
		PreviousSessionKeys: []IdentitySessionHMACKey{{
			Version: "v1", Key: previousKey,
			RetireAt: now.Add(defaultIdentityRefreshSessionTTL + 24*time.Hour),
		}},
		LegacySessionKeyVersion:     "v1",
		RequirePreviousKeyRetention: true,
		PreviousKeyRetentionMargin:  24 * time.Hour,
		Now:                         func() time.Time { return now },
		SQLTimeout:                  8 * time.Second,
		StatementTimeout:            5 * time.Second,
		LockTimeout:                 time.Second,
	}
	store, err := NewProductionIdentityStore(base)
	if err != nil {
		t.Fatal(err)
	}
	readiness := store.SessionKeyringReadiness()
	if !readiness.Ready || readiness.ActiveVersion != "v2" ||
		readiness.LegacyVersion != "v1" || len(readiness.PreviousKeys) != 1 ||
		!readiness.PreviousKeys[0].RetentionReady ||
		readiness.PreviousKeys[0].RemainingSeconds <= 0 {
		t.Fatalf("unexpected public-safe keyring readiness: %#v", readiness)
	}
	store.sessionTokens.close()

	unsafe := base
	unsafe.PreviousSessionKeys = []IdentitySessionHMACKey{{
		Version: "v1", Key: previousKey,
		RetireAt: now.Add(defaultIdentityRefreshSessionTTL),
	}}
	if _, err := NewProductionIdentityStore(unsafe); err == nil ||
		!strings.Contains(err.Error(), "retires before live refresh tokens expire") {
		t.Fatalf("unsafe previous-key retirement accepted: %v", err)
	}
	unsafe = base
	unsafe.PreviousSessionKeys = []IdentitySessionHMACKey{{Version: "v1", Key: previousKey}}
	if _, err := NewProductionIdentityStore(unsafe); err == nil ||
		!strings.Contains(err.Error(), "missing retirement metadata") {
		t.Fatalf("missing previous-key retirement accepted: %v", err)
	}
	unsafe = base
	unsafe.LockTimeout = 6 * time.Second
	if _, err := NewProductionIdentityStore(unsafe); err == nil ||
		!strings.Contains(err.Error(), "lock <= statement <= operation") {
		t.Fatalf("unsafe timeout ordering accepted: %v", err)
	}
}

func TestProductionIdentityStoreReadyFailsClosedOnIncompleteSchema(t *testing.T) {
	db, mock, err := sqlmock.New(sqlmock.MonitorPingsOption(true))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: []byte("01234567890123456789012345678901"),
	})
	if err != nil {
		t.Fatal(err)
	}
	mock.ExpectPing()
	mock.ExpectQuery(regexp.QuoteMeta(productionIdentityReadinessQuery)).
		WillReturnRows(sqlmock.NewRows([]string{"ready"}).AddRow(false))
	if err := store.Ready(context.Background()); err == nil {
		t.Fatal("expected incomplete schema to fail")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentityStoreReadyRequiresSuccessfulSchemaVerification(t *testing.T) {
	t.Run("complete schema", func(t *testing.T) {
		db, mock, err := sqlmock.New(sqlmock.MonitorPingsOption(true))
		if err != nil {
			t.Fatal(err)
		}
		defer db.Close()
		store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
			DB: db, SessionKey: []byte("01234567890123456789012345678901"),
		})
		if err != nil {
			t.Fatal(err)
		}
		mock.ExpectPing()
		mock.ExpectQuery(regexp.QuoteMeta(productionIdentityReadinessQuery)).
			WillReturnRows(sqlmock.NewRows([]string{"ready"}).AddRow(true))
		if err := store.Ready(context.Background()); err != nil {
			t.Fatalf("complete production identity schema rejected: %v", err)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})

	t.Run("verification query failure", func(t *testing.T) {
		db, mock, err := sqlmock.New(sqlmock.MonitorPingsOption(true))
		if err != nil {
			t.Fatal(err)
		}
		defer db.Close()
		store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
			DB: db, SessionKey: []byte("01234567890123456789012345678901"),
		})
		if err != nil {
			t.Fatal(err)
		}
		mock.ExpectPing()
		mock.ExpectQuery(regexp.QuoteMeta(productionIdentityReadinessQuery)).
			WillReturnError(errors.New("catalog unavailable"))
		err = store.Ready(context.Background())
		if err == nil || !strings.Contains(err.Error(), "verify production identity schema") {
			t.Fatalf("schema verification failure did not fail closed: %v", err)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
}

func TestProductionIdentityReadinessRequiresSessionAndDeliveryReplacementContracts(t *testing.T) {
	for _, required := range []string{
		"identity_session_lifecycle_operations",
		"identity_verification_delivery_redrive_audit",
		"a1_issue_identity_verification_challenge_with_delivery",
		"a1_issue_identity_session_with_refresh",
		"a1_rotate_identity_session_refresh",
		"a1_rotate_identity_session_refresh_from_digest",
		"a1_revoke_identity_session",
		"a1_revoke_all_identity_sessions",
		"a1_login_with_verified_identity_with_refresh",
		"a1_recover_verified_identity_with_refresh",
		"a1_claim_identity_delivery_outbox",
		"a1_heartbeat_identity_delivery_outbox",
		"a1_complete_identity_delivery_outbox",
		"a1_retry_identity_delivery_outbox",
		"a1_dead_letter_identity_delivery_outbox",
		"a1_redrive_identity_delivery_outbox",
	} {
		if !strings.Contains(productionIdentityReadinessQuery, required) {
			t.Fatalf("readiness omitted %s", required)
		}
	}
	for _, revoked := range []string{
		"public.a1_login_with_verified_identity(",
		"public.a1_recover_verified_identity(",
		"public.a1_issue_identity_session(",
		"public.a1_issue_identity_verification_challenge(",
	} {
		if strings.Contains(productionIdentityReadinessQuery, revoked) {
			t.Fatalf("readiness still depends on revoked runtime entrypoint %s", revoked)
		}
	}
}

func TestProductionIdentityReadinessEnforcesSecurityAuthorityLeastPrivilege(t *testing.T) {
	for _, required := range []string{
		"NOT has_function_privilege",
		"a1_issue_identity_security_mutation_ticket",
		"a1_consume_identity_security_receipt",
		"a1_mutate_account_password",
		"a1_begin_totp_enrollment",
		"a1_confirm_totp_enrollment",
		"a1_set_account_two_factor",
		"NOT has_table_privilege",
		"identity_account_security",
		"relrowsecurity",
		"relforcerowsecurity",
		"p.prosecdef",
		"pg_get_userbyid(p.proowner) <> current_user",
		"search_path=pg_catalog,public",
	} {
		if !strings.Contains(productionIdentityReadinessQuery, required) {
			t.Fatalf("security readiness omitted %s", required)
		}
	}
}

func TestProductionIdentityStoreResolvesOneTrustedSessionForAllInterfaces(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	key := []byte("01234567890123456789012345678901")
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{DB: db, SessionKey: key})
	if err != nil {
		t.Fatal(err)
	}
	token := "opaque-session-token"
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(token))
	digest := hex.EncodeToString(mac.Sum(nil))
	columns := []string{"account", "actor", "session", "tenant", "project", "user"}
	for index := 0; index < 3; index++ {
		mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").WithArgs(digest).WillReturnRows(
			sqlmock.NewRows(columns).AddRow(
				"principal-1", "principal-1", "session-1", "tenant-1", "project-1",
				"principal-1",
			),
		)
	}
	request, _ := http.NewRequest(http.MethodGet, "https://api.example.test/v1/accounts/principal-1", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	identitySession, err := store.ResolveIdentityHTTPSession(context.Background(), request)
	if err != nil || identitySession.AccountID != "principal-1" {
		t.Fatalf("identity session: %#v, %v", identitySession, err)
	}
	oauthSession, err := store.ResolveOAuthSession(context.Background(), request)
	if err != nil || oauthSession.TenantID != "tenant-1" {
		t.Fatalf("OAuth session: %#v, %v", oauthSession, err)
	}
	githubSession, err := store.ResolveGitHubOAuthSession(context.Background(), request)
	if err != nil || githubSession.TenantID != "tenant-1" || githubSession.AccountID != "principal-1" {
		t.Fatalf("GitHub session: %#v, %v", githubSession, err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentityStoreSessionHMACIsKeyedAndNeverQueriesRawToken(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	key := []byte("01234567890123456789012345678901")
	otherKey := []byte("abcdefghijklmnopqrstuvwxyzABCDEF")
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{DB: db, SessionKey: key})
	if err != nil {
		t.Fatal(err)
	}
	otherStore, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{DB: db, SessionKey: otherKey})
	if err != nil {
		t.Fatal(err)
	}
	token := "raw-session-material-that-must-not-reach-postgres"
	digest := store.sessionDigest(token)
	if digest == token || digest == otherStore.sessionDigest(token) || len(digest) != sha256.Size*2 {
		t.Fatalf("session digest is not a keyed SHA-256 boundary: %q", digest)
	}

	mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
		WithArgs(digest).
		WillReturnError(errors.New("database unavailable"))
	request, _ := http.NewRequest(http.MethodGet, "https://api.example.test", nil)
	request.Header.Set("Authorization", "Bearer "+token)
	if _, err := store.ResolveIdentityHTTPSession(context.Background(), request); err == nil {
		t.Fatal("database failure must fail session resolution closed")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentityStoreSessionKeyRotationResolvesVersionedAndLegacyBearers(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	activeKey := bytes.Repeat([]byte{0x32}, 32)
	previousKey := bytes.Repeat([]byte{0x18}, 32)
	activeNonce := bytes.Repeat([]byte{0x61}, identitySessionNonceBytes)
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: activeKey, SessionKeyVersion: "v2",
		PreviousSessionKeys:     []IdentitySessionHMACKey{{Version: "v1", Key: previousKey}},
		LegacySessionKeyVersion: "v1",
		Random:                  bytes.NewReader(activeNonce),
	})
	if err != nil {
		db.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = store.Close() })

	issued, err := store.sessionTokens.issue()
	if err != nil {
		t.Fatal(err)
	}
	if issued.keyVersion != "v2" ||
		issued.bearer != identitySessionBearerPrefix+".v2."+base64.RawURLEncoding.EncodeToString(activeNonce) ||
		issued.digest != identitySessionHMAC(activeKey, issued.bearer) {
		t.Fatal("new bearer did not use the active key version and digest")
	}
	previousNonce := bytes.Repeat([]byte{0x62}, identitySessionNonceBytes)
	previousBearer := identitySessionBearerPrefix + ".v1." +
		base64.RawURLEncoding.EncodeToString(previousNonce)
	legacyBearer := "legacy-session-bearer"

	for index, test := range []struct {
		bearer string
		digest string
	}{
		{bearer: issued.bearer, digest: identitySessionHMAC(activeKey, issued.bearer)},
		{bearer: previousBearer, digest: identitySessionHMAC(previousKey, previousBearer)},
		{bearer: legacyBearer, digest: identitySessionHMAC(previousKey, legacyBearer)},
	} {
		mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
			WithArgs(test.digest).
			WillReturnRows(sqlmock.NewRows(
				[]string{"account", "actor", "session", "tenant", "project", "user"},
			).AddRow(
				"principal-1", "principal-1", fmt.Sprintf("session-%d", index),
				"tenant-1", "project-1", "principal-1",
			))
		request, _ := http.NewRequest(http.MethodGet, "https://api.example.test", nil)
		request.Header.Set("Authorization", "Bearer "+test.bearer)
		resolved, resolveErr := store.ResolveIdentityHTTPSession(context.Background(), request)
		if resolveErr != nil || resolved.SessionID != fmt.Sprintf("session-%d", index) {
			t.Fatalf("resolve rotation case %d: session=%#v err=%v", index, resolved, resolveErr)
		}
	}

	unknownBearer := identitySessionBearerPrefix + ".v3." +
		base64.RawURLEncoding.EncodeToString(previousNonce)
	request, _ := http.NewRequest(http.MethodGet, "https://api.example.test", nil)
	request.Header.Set("Authorization", "Bearer "+unknownBearer)
	if _, err := store.ResolveIdentityHTTPSession(context.Background(), request); err == nil {
		t.Fatal("unknown session key version reached the database")
	}
	refreshBearer := identityRefreshBearerPrefix + ".v2." +
		base64.RawURLEncoding.EncodeToString(previousNonce)
	refreshDigest, refreshVersion, err := store.sessionTokens.digestRefresh(refreshBearer)
	if err != nil || refreshVersion != "v2" ||
		refreshDigest != identitySessionHMAC(activeKey, refreshBearer) {
		t.Fatalf("refresh digest lineage failed: version=%q err=%v", refreshVersion, err)
	}
	refreshRequest, _ := http.NewRequest(http.MethodGet, "https://api.example.test", nil)
	refreshRequest.Header.Set("Authorization", "Bearer "+refreshBearer)
	if _, err := store.ResolveIdentityHTTPSession(context.Background(), refreshRequest); err == nil {
		t.Fatal("refresh bearer reached the access-session database boundary")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentityStoreRejectsSessionsRejectedByAuthenticationBoundary(t *testing.T) {
	for _, reason := range []string{
		"revoked session",
		"expired session",
		"inactive principal",
		"disabled credential",
		"login-disabled credential",
		"credential ownership mismatch",
		"suspended organization membership",
		"revoked project membership",
	} {
		t.Run(reason, func(t *testing.T) {
			db, mock, err := sqlmock.New()
			if err != nil {
				t.Fatal(err)
			}
			defer db.Close()
			store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
				DB: db, SessionKey: []byte("01234567890123456789012345678901"),
			})
			if err != nil {
				t.Fatal(err)
			}
			token := "inactive-session-token"
			mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
				WithArgs(store.sessionDigest(token)).
				WillReturnRows(sqlmock.NewRows(
					[]string{"account", "actor", "session", "tenant", "project", "user"},
				))
			request, _ := http.NewRequest(http.MethodGet, "https://api.example.test", nil)
			request.Header.Set("Authorization", "Bearer "+token)
			if _, err := store.ResolveIdentityHTTPSession(context.Background(), request); err == nil ||
				!strings.Contains(err.Error(), "invalid") {
				t.Fatalf("%s did not fail closed: %v", reason, err)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestProductionIdentityStoreRejectsMalformedBearerWithoutDatabaseRead(t *testing.T) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: []byte("01234567890123456789012345678901"),
	})
	if err != nil {
		t.Fatal(err)
	}
	request, _ := http.NewRequest(http.MethodGet, "https://api.example.test", nil)
	request.Header.Set("Authorization", "Basic forbidden")
	if _, err := store.ResolveIdentityHTTPSession(context.Background(), request); err == nil {
		t.Fatal("expected malformed bearer to fail")
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}
