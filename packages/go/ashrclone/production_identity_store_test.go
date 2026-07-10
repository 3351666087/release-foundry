package ashrclone

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
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
	columns := []string{"account", "actor", "session", "tenant", "project", "user", "status", "expires"}
	for index := 0; index < 3; index++ {
		mock.ExpectQuery("FROM identity_sessions").WithArgs(digest).WillReturnRows(
			sqlmock.NewRows(columns).AddRow(
				"principal-1", "principal-1", "session-1", "tenant-1", "project-1",
				"principal-1", "active", time.Now().UTC().Add(time.Hour),
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

	mock.ExpectQuery("FROM identity_sessions").
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

func TestProductionIdentityStoreRejectsInactiveAndExpiredSessions(t *testing.T) {
	for _, test := range []struct {
		name      string
		status    string
		expiresAt time.Time
	}{
		{name: "revoked", status: "revoked", expiresAt: time.Now().UTC().Add(time.Hour)},
		{name: "expired", status: "active", expiresAt: time.Now().UTC().Add(-time.Minute)},
	} {
		t.Run(test.name, func(t *testing.T) {
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
			mock.ExpectQuery("FROM identity_sessions").
				WithArgs(store.sessionDigest(token)).
				WillReturnRows(sqlmock.NewRows(
					[]string{"account", "actor", "session", "tenant", "project", "user", "status", "expires"},
				).AddRow(
					"principal-1", "principal-1", "session-1", "tenant-1", "project-1",
					"principal-1", test.status, test.expiresAt,
				))
			request, _ := http.NewRequest(http.MethodGet, "https://api.example.test", nil)
			request.Header.Set("Authorization", "Bearer "+token)
			if _, err := store.ResolveIdentityHTTPSession(context.Background(), request); err == nil ||
				!strings.Contains(err.Error(), "inactive") {
				t.Fatalf("%s session did not fail closed: %v", test.name, err)
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
