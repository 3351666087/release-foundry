package ashrclone

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
	"regexp"
	"strings"
	"testing"

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
