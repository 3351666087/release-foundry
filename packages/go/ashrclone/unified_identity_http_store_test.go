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

var _ UnifiedIdentityHTTPStore = identityHTTPStoreBackend{}
