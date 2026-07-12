package ashrclone

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

type identityHTTPStoreBackend struct {
	ControlPlaneBackend
	account IdentityAccountDTO
}

func (backend identityHTTPStoreBackend) GetIdentityAccount(
	_ context.Context,
	accountID string,
) (IdentityAccountDTO, error) {
	if accountID != backend.account.AccountID {
		return IdentityAccountDTO{}, ErrIdentityAccountNotFound
	}
	return backend.account, nil
}

func TestUnifiedIdentityHTTPReadsThroughAbstractIdentityStore(t *testing.T) {
	now := time.Date(2026, 7, 11, 10, 0, 0, 0, time.UTC)
	backend := identityHTTPStoreBackend{
		ControlPlaneBackend: NewMemoryService(),
		account: IdentityAccountDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion,
			AccountID:     "acct_http_store",
			PrimaryID:     "prn_http_store",
			DisplayName:   "HTTP Store",
			Status:        "active",
			Credentials: []IdentityCredentialDTO{{
				SchemaVersion: UnifiedIdentitySchemaVersion,
				CredentialID:  "cred_http_store",
				Kind:          IdentityCredentialEmail,
				Provider:      IdentityProviderLocal,
				Verified:      true,
				CanLogin:      true,
				LinkedAt:      now,
			}},
			CredentialCount: 1,
			CreatedAt:       now,
			UpdatedAt:       now,
		},
	}

	handler := NewHTTPServerWithOptions(backend, HTTPServerOptions{
		UnifiedIdentityStore: backend,
		IdentitySessions: identityHTTPTestSessionResolver{session: IdentityHTTPSession{
			AccountID: backend.account.AccountID,
			ActorID:   backend.account.AccountID,
			SessionID: "session-http-store",
		}},
	})
	request := httptest.NewRequest(http.MethodGet, "/v1/accounts/"+backend.account.AccountID+"/credentials", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("abstract identity store status=%d body=%s", response.Code, response.Body.String())
	}
	if !strings.Contains(response.Body.String(), backend.account.AccountID) ||
		!strings.Contains(response.Body.String(), backend.account.Credentials[0].CredentialID) {
		t.Fatalf("abstract identity store response omitted account data: %s", response.Body.String())
	}
}

func TestUnifiedIdentityHTTPStoreMustBeExplicit(t *testing.T) {
	accountID := "acct_explicit_only"
	backend := identityHTTPStoreBackend{
		ControlPlaneBackend: NewMemoryService(),
		account:             IdentityAccountDTO{AccountID: accountID},
	}
	handler := NewHTTPServerWithOptions(backend, HTTPServerOptions{
		IdentitySessions: identityHTTPTestSessionResolver{session: IdentityHTTPSession{
			AccountID: accountID,
			ActorID:   accountID,
			SessionID: "session-explicit-only",
		}},
	})
	request := httptest.NewRequest(http.MethodGet, "/v1/accounts/"+accountID, nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusServiceUnavailable ||
		!strings.Contains(response.Body.String(), "identity_store_unavailable") {
		t.Fatalf("implicit backend store was used: status=%d body=%s", response.Code, response.Body.String())
	}
}

func TestUnifiedIdentityHTTPExplicitStorePrecedesDevelopmentService(t *testing.T) {
	now := time.Date(2026, 7, 12, 8, 0, 0, 0, time.UTC)
	development, err := NewUnifiedIdentityService(UnifiedIdentityServiceOptions{
		FingerprintKey: []byte("01234567890123456789012345678901"),
		Now:            func() time.Time { return now },
	})
	if err != nil {
		t.Fatal(err)
	}
	explicit := identityHTTPStoreBackend{
		ControlPlaneBackend: NewMemoryService(),
		account: IdentityAccountDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion,
			AccountID:     "acct_explicit_priority",
			DisplayName:   "Explicit Store",
			Status:        "active",
			CreatedAt:     now,
			UpdatedAt:     now,
		},
	}
	handler := NewHTTPServerWithOptions(NewMemoryService(), HTTPServerOptions{
		UnifiedIdentity:      development,
		UnifiedIdentityStore: explicit,
		IdentitySessions: identityHTTPTestSessionResolver{session: IdentityHTTPSession{
			AccountID: explicit.account.AccountID,
			ActorID:   explicit.account.AccountID,
			SessionID: "session-explicit-priority",
		}},
	})
	request := httptest.NewRequest(http.MethodGet, "/v1/accounts/"+explicit.account.AccountID, nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK || !strings.Contains(response.Body.String(), "Explicit Store") {
		t.Fatalf("explicit store did not take precedence: status=%d body=%s", response.Code, response.Body.String())
	}
}

var _ UnifiedIdentityHTTPStore = identityHTTPStoreBackend{}
