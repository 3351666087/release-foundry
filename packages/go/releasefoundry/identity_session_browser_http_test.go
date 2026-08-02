package releasefoundry

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
)

const (
	browserSessionOrganizationID = "11111111-1111-4111-8111-111111111111"
	browserSessionProjectID      = "22222222-2222-4222-8222-222222222222"
	browserSessionAccountID      = "33333333-3333-4333-8333-333333333333"
	browserSessionNewID          = "44444444-4444-4444-8444-444444444444"
)

type browserSessionIdentityBackend struct {
	*MemoryService
	account IdentityAccountDTO
}

func (backend *browserSessionIdentityBackend) GetIdentityAccount(
	_ context.Context,
	accountID string,
) (IdentityAccountDTO, error) {
	if backend == nil || accountID != backend.account.AccountID {
		return IdentityAccountDTO{}, fmt.Errorf("identity account is unavailable")
	}
	return backend.account, nil
}

func TestBrowserLoginCookieRefreshAndProtectedRouteLifecycle(t *testing.T) {
	now := time.Date(2026, 7, 11, 18, 0, 0, 0, time.UTC)
	sessionKey := bytes.Repeat([]byte{0x42}, 32)

	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: db, SessionKey: sessionKey, SessionKeyVersion: "v2",
		Now: func() time.Time { return now },
	})
	if err != nil {
		db.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = store.Close() })

	transport, err := NewIdentitySessionCookieTransport(IdentitySessionCookieTransportOptions{
		Now: func() time.Time { return now },
	})
	if err != nil {
		t.Fatal(err)
	}
	coordinator := &httpSessionVerificationCoordinator{now: now}
	vault := &httpSessionVerificationVault{}
	verification, err := NewIdentityVerificationService(IdentityVerificationServiceOptions{
		Store:                  &httpSessionVerificationStore{},
		DeliveryVaultSealer:    vault,
		DeliveryVaultDeleter:   vault,
		DeliveryMode:           IdentityVerificationDeliveryTransactionalOutbox,
		TransactionCoordinator: coordinator,
		Now:                    func() time.Time { return now },
		DigestKey:              []byte("browser-session-verification-key-32"),
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(verification.Close)
	account := IdentityAccountDTO{
		SchemaVersion: UnifiedIdentitySchemaVersion,
		AccountID:     browserSessionAccountID,
		PrimaryID:     browserSessionAccountID,
		Status:        "active",
		Credentials:   []IdentityCredentialDTO{},
		Memberships:   []IdentityMembershipDTO{},
		CreatedAt:     now,
		UpdatedAt:     now,
	}
	backend := &browserSessionIdentityBackend{
		MemoryService: NewMemoryService(),
		account:       account,
	}
	handler := NewHTTPServerWithOptions(backend, HTTPServerOptions{
		UnifiedIdentityStore:            backend,
		IdentitySessions:                store,
		IdentityVerification:            verification,
		IdentitySessionReceiptTransport: transport,
	})

	loginBody := fmt.Sprintf(
		`{"challenge_id":"browser-login","code":"123456","channel":"email","identifier":"person@example.test","purpose":"login","tenant_id":"tenant-http","account_id":%q}`,
		browserSessionAccountID,
	)
	loginRequest := httptest.NewRequest(
		http.MethodPost,
		"https://api.example.test/v1/identity-verification/verify",
		strings.NewReader(loginBody),
	)
	loginResponse := httptest.NewRecorder()
	handler.ServeHTTP(loginResponse, loginRequest)
	if loginResponse.Code != http.StatusOK {
		t.Fatalf("login status=%d body=%s", loginResponse.Code, loginResponse.Body.String())
	}
	loginCookies := cookiesByName(loginResponse.Result().Cookies())
	oldAccess := loginCookies[IdentitySessionCookieName]
	oldRefresh := loginCookies[IdentityRefreshCookieName]
	if oldAccess == nil || oldRefresh == nil {
		t.Fatalf("login omitted browser session cookies: %#v", loginCookies)
	}

	oldAccessDigest := identitySessionHMAC(sessionKey, oldAccess.Value)
	mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
		WithArgs(oldAccessDigest).
		WillReturnRows(browserSessionRows("session-before-refresh"))
	insecureProtectedRequest := httptest.NewRequest(
		http.MethodGet,
		"http://api.example.test/v1/accounts/"+browserSessionAccountID,
		nil,
	)
	insecureProtectedRequest.AddCookie(oldAccess)
	insecureProtectedResponse := httptest.NewRecorder()
	handler.ServeHTTP(insecureProtectedResponse, insecureProtectedRequest)
	if insecureProtectedResponse.Code != http.StatusUnauthorized {
		t.Fatalf("secure cookie was accepted over plaintext HTTP: %d", insecureProtectedResponse.Code)
	}
	protectedRequest := httptest.NewRequest(
		http.MethodGet,
		"https://api.example.test/v1/accounts/"+browserSessionAccountID,
		nil,
	)
	protectedRequest.AddCookie(oldAccess)
	protectedResponse := httptest.NewRecorder()
	handler.ServeHTTP(protectedResponse, protectedRequest)
	if protectedResponse.Code != http.StatusOK {
		t.Fatalf("login cookie did not authenticate protected route: %d %s", protectedResponse.Code, protectedResponse.Body.String())
	}

	conflictRequest := httptest.NewRequest(
		http.MethodGet,
		"https://api.example.test/v1/accounts/"+browserSessionAccountID,
		nil,
	)
	conflictRequest.AddCookie(oldAccess)
	conflictRequest.Header.Set(
		"Authorization",
		"Bearer releasefoundry_session.v2."+strings.Repeat("Z", 43),
	)
	conflictResponse := httptest.NewRecorder()
	handler.ServeHTTP(conflictResponse, conflictRequest)
	if conflictResponse.Code != http.StatusUnauthorized {
		t.Fatalf("conflicting header and cookie reached the session store: %d", conflictResponse.Code)
	}
	crossOriginRequest := browserRefreshRequest(
		oldAccess, oldRefresh, "browser-refresh-cross-origin",
	)
	crossOriginRequest.Header.Set("Origin", "https://attacker.example.test")
	crossOriginRequest.Header.Set("Sec-Fetch-Site", "cross-site")
	crossOriginResponse := httptest.NewRecorder()
	handler.ServeHTTP(crossOriginResponse, crossOriginRequest)
	if crossOriginResponse.Code != http.StatusForbidden {
		t.Fatalf("cross-origin refresh was accepted: %d", crossOriginResponse.Code)
	}
	ambiguousRefreshRequest := browserRefreshRequest(
		oldAccess, oldRefresh, "browser-refresh-ambiguous",
	)
	ambiguousRefreshRequest.Header.Set("Authorization", "Bearer "+oldAccess.Value)
	ambiguousRefreshResponse := httptest.NewRecorder()
	handler.ServeHTTP(ambiguousRefreshResponse, ambiguousRefreshRequest)
	if ambiguousRefreshResponse.Code != http.StatusUnauthorized {
		t.Fatalf("header-bearing refresh reached PostgreSQL: %d", ambiguousRefreshResponse.Code)
	}

	idempotencyKey := "browser-refresh-0001"
	newAccessToken, newRefreshToken, err := store.sessionTokens.deriveRefreshRotation(
		oldRefresh.Value,
		idempotencyKey,
	)
	if err != nil {
		t.Fatal(err)
	}
	newAccessBearer := newAccessToken.bearer
	newRefreshBearer := newRefreshToken.bearer
	newAccessDigest := identitySessionHMAC(sessionKey, newAccessBearer)
	newRefreshDigest := identitySessionHMAC(sessionKey, newRefreshBearer)
	oldRefreshDigest := identitySessionHMAC(sessionKey, oldRefresh.Value)
	requestedAccessExpiresAt := now.Add(defaultIdentityAccessSessionTTL)
	refreshExpiresAt := now.Add(defaultIdentityRefreshSessionTTL)
	idempotencyDigest, err := store.sessionTokens.digestActive(
		"identity-refresh-idempotency",
		browserSessionProjectID,
		browserSessionAccountID,
		idempotencyKey,
	)
	if err != nil {
		t.Fatal(err)
	}
	requestDigest, err := store.sessionTokens.digestActive(
		"identity-refresh-request",
		browserSessionProjectID,
		browserSessionAccountID,
		oldRefreshDigest,
		newAccessDigest,
		newRefreshDigest,
	)
	if err != nil {
		t.Fatal(err)
	}
	expectIdentitySessionRefreshTransaction(mock)
	mock.ExpectQuery("FROM a1_rotate_identity_session_refresh_from_digest").
		WithArgs(
			browserSessionProjectID,
			browserSessionAccountID,
			oldRefreshDigest,
			newAccessDigest,
			newRefreshDigest,
			requestedAccessExpiresAt,
			idempotencyDigest,
			requestDigest,
			`{"source":"go_identity_session_refresh_http"}`,
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"session_id", "organization_id", "project_id", "principal_id",
			"rotation_generation", "outcome_code", "affected_count",
			"access_expires_at", "refresh_expires_at",
		}).AddRow(
			browserSessionNewID,
			browserSessionOrganizationID,
			browserSessionProjectID,
			browserSessionAccountID,
			1,
			"rotated",
			1,
			requestedAccessExpiresAt,
			refreshExpiresAt,
		))
	mock.ExpectCommit()
	refreshRequest := browserRefreshRequest(oldAccess, oldRefresh, idempotencyKey)
	refreshResponse := httptest.NewRecorder()
	handler.ServeHTTP(refreshResponse, refreshRequest)
	if refreshResponse.Code != http.StatusOK {
		t.Fatalf("refresh status=%d body=%s", refreshResponse.Code, refreshResponse.Body.String())
	}
	if strings.Contains(refreshResponse.Body.String(), newAccessBearer) ||
		strings.Contains(refreshResponse.Body.String(), newRefreshBearer) {
		t.Fatal("refresh response body exposed bearer material")
	}
	refreshedCookies := cookiesByName(refreshResponse.Result().Cookies())
	newAccess := refreshedCookies[IdentitySessionCookieName]
	newRefresh := refreshedCookies[IdentityRefreshCookieName]
	if newAccess == nil || newRefresh == nil ||
		newAccess.Value != newAccessBearer || newRefresh.Value != newRefreshBearer {
		t.Fatalf("refresh did not atomically replace both cookies: %#v", refreshedCookies)
	}

	restartDB, restartMock, err := sqlmock.New()
	if err != nil {
		t.Fatal(err)
	}
	restartStore, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB: restartDB, SessionKey: bytes.Repeat([]byte{0x43}, 32),
		SessionKeyVersion: "v3",
		PreviousSessionKeys: []IdentitySessionHMACKey{{
			Version: "v2",
			Key:     sessionKey,
		}},
		Now: func() time.Time { return now },
	})
	if err != nil {
		_ = restartDB.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = restartStore.Close() })
	restartAccessToken, restartRefreshToken, err := restartStore.sessionTokens.deriveRefreshRotation(
		oldRefresh.Value,
		idempotencyKey,
	)
	if err != nil {
		t.Fatal(err)
	}
	if restartAccessToken.bearer != newAccessBearer ||
		restartRefreshToken.bearer != newRefreshBearer ||
		restartAccessToken.keyVersion != "v2" ||
		restartRefreshToken.keyVersion != "v2" {
		t.Fatal("active-key rotation changed the idempotent replacement pair")
	}
	restartHandler := NewHTTPServerWithOptions(backend, HTTPServerOptions{
		IdentitySessions:                restartStore,
		IdentityVerification:            verification,
		IdentitySessionReceiptTransport: transport,
	})

	now = now.Add(30 * time.Second)
	replayRequestedAccessExpiresAt := now.Add(defaultIdentityAccessSessionTTL)
	expectIdentitySessionRefreshTransaction(restartMock)
	restartMock.ExpectQuery("FROM a1_rotate_identity_session_refresh_from_digest").
		WithArgs(
			browserSessionProjectID,
			browserSessionAccountID,
			oldRefreshDigest,
			newAccessDigest,
			newRefreshDigest,
			replayRequestedAccessExpiresAt,
			idempotencyDigest,
			requestDigest,
			`{"source":"go_identity_session_refresh_http"}`,
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"session_id", "organization_id", "project_id", "principal_id",
			"rotation_generation", "outcome_code", "affected_count",
			"access_expires_at", "refresh_expires_at",
		}).AddRow(
			browserSessionNewID,
			browserSessionOrganizationID,
			browserSessionProjectID,
			browserSessionAccountID,
			1,
			"rotated",
			1,
			requestedAccessExpiresAt,
			refreshExpiresAt,
		))
	restartMock.ExpectCommit()
	replayRequest := browserRefreshRequest(oldAccess, oldRefresh, idempotencyKey)
	replayResponse := httptest.NewRecorder()
	restartHandler.ServeHTTP(replayResponse, replayRequest)
	if replayResponse.Code != http.StatusOK {
		t.Fatalf("idempotent refresh replay status=%d body=%s", replayResponse.Code, replayResponse.Body.String())
	}
	replayedCookies := cookiesByName(replayResponse.Result().Cookies())
	for _, name := range []string{IdentitySessionCookieName, IdentityRefreshCookieName} {
		originalCookie := refreshedCookies[name]
		replayedCookie := replayedCookies[name]
		if originalCookie == nil || replayedCookie == nil ||
			originalCookie.Value != replayedCookie.Value ||
			!originalCookie.Expires.Equal(replayedCookie.Expires) ||
			originalCookie.Path != replayedCookie.Path ||
			originalCookie.Secure != replayedCookie.Secure ||
			originalCookie.HttpOnly != replayedCookie.HttpOnly ||
			originalCookie.SameSite != replayedCookie.SameSite ||
			replayedCookie.MaxAge != originalCookie.MaxAge-30 {
			t.Fatalf("idempotent refresh replay changed replacement cookie %s: original=%#v replay=%#v", name, originalCookie, replayedCookie)
		}
	}
	if err := restartMock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}

	mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
		WithArgs(oldAccessDigest).
		WillReturnRows(sqlmock.NewRows(browserSessionColumns()))
	oldAccessRequest := httptest.NewRequest(
		http.MethodGet,
		"https://api.example.test/v1/accounts/"+browserSessionAccountID,
		nil,
	)
	oldAccessRequest.AddCookie(oldAccess)
	oldAccessResponse := httptest.NewRecorder()
	handler.ServeHTTP(oldAccessResponse, oldAccessRequest)
	if oldAccessResponse.Code != http.StatusUnauthorized {
		t.Fatalf("rotated access cookie remained valid: %d", oldAccessResponse.Code)
	}

	mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
		WithArgs(newAccessDigest).
		WillReturnRows(browserSessionRows(browserSessionNewID))
	newAccessRequest := httptest.NewRequest(
		http.MethodGet,
		"https://api.example.test/v1/accounts/"+browserSessionAccountID,
		nil,
	)
	newAccessRequest.AddCookie(newAccess)
	newAccessResponse := httptest.NewRecorder()
	handler.ServeHTTP(newAccessResponse, newAccessRequest)
	if newAccessResponse.Code != http.StatusOK {
		t.Fatalf("rotated access cookie was rejected: %d %s", newAccessResponse.Code, newAccessResponse.Body.String())
	}

	mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
		WithArgs(newAccessDigest).
		WillReturnRows(browserSessionRows(browserSessionNewID))
	meRequest := httptest.NewRequest(http.MethodGet, "https://api.example.test/v1/me", nil)
	meRequest.AddCookie(newAccess)
	meResponse := httptest.NewRecorder()
	handler.ServeHTTP(meResponse, meRequest)
	if meResponse.Code != http.StatusOK ||
		!strings.Contains(meResponse.Body.String(), browserSessionAccountID) ||
		strings.Contains(meResponse.Body.String(), newAccess.Value) {
		t.Fatalf("cookie identity read was unsafe: %d %s", meResponse.Code, meResponse.Body.String())
	}

	mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
		WithArgs(newAccessDigest).
		WillReturnRows(browserSessionRows(browserSessionNewID))
	mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
		WithArgs(newAccessDigest).
		WillReturnRows(browserSessionRows(browserSessionNewID))
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config\\('statement_timeout'").
		WithArgs("5000ms", "2000ms", browserSessionOrganizationID,
			browserSessionProjectID, browserSessionAccountID).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectQuery("FROM a1_revoke_all_identity_sessions").
		WithArgs(
			browserSessionOrganizationID,
			browserSessionProjectID,
			browserSessionAccountID,
			newAccessDigest,
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"session_id", "rotation_generation", "outcome_code", "affected_count",
		}).AddRow(browserSessionNewID, 1, "revoked_all", 1))
	mock.ExpectCommit()
	logoutRequest := httptest.NewRequest(
		http.MethodPost,
		"https://api.example.test/v1/identity/sessions/revoke",
		strings.NewReader("{}"),
	)
	logoutRequest.Header.Set("Origin", "https://api.example.test")
	logoutRequest.Header.Set("Sec-Fetch-Site", "same-origin")
	logoutRequest.AddCookie(newAccess)
	logoutRequest.AddCookie(newRefresh)
	logoutResponse := httptest.NewRecorder()
	handler.ServeHTTP(logoutResponse, logoutRequest)
	if logoutResponse.Code != http.StatusOK ||
		!strings.Contains(logoutResponse.Body.String(), `"status":"revoked"`) {
		t.Fatalf("cookie logout failed: %d %s", logoutResponse.Code, logoutResponse.Body.String())
	}
	clearedCookies := cookiesByName(logoutResponse.Result().Cookies())
	for _, name := range []string{IdentitySessionCookieName, IdentityRefreshCookieName} {
		cookie := clearedCookies[name]
		if cookie == nil || cookie.MaxAge != -1 || cookie.Value != "" ||
			!cookie.Secure || !cookie.HttpOnly || cookie.Path != "/" {
			t.Fatalf("logout did not securely clear %s: %#v", name, cookie)
		}
	}

	mock.ExpectQuery("FROM a1_authenticate_identity_session_digest").
		WithArgs(newAccessDigest).
		WillReturnRows(sqlmock.NewRows(browserSessionColumns()))
	revokedMeRequest := httptest.NewRequest(http.MethodGet, "https://api.example.test/v1/me", nil)
	revokedMeRequest.AddCookie(newAccess)
	revokedMeResponse := httptest.NewRecorder()
	handler.ServeHTTP(revokedMeResponse, revokedMeRequest)
	if revokedMeResponse.Code != http.StatusUnauthorized {
		t.Fatalf("revoked cookie still authorized /v1/me: %d", revokedMeResponse.Code)
	}

	reuseIdempotencyKey := "browser-refresh-reuse-0002"
	reuseAccessToken, reuseRefreshToken, err := store.sessionTokens.deriveRefreshRotation(
		oldRefresh.Value,
		reuseIdempotencyKey,
	)
	if err != nil {
		t.Fatal(err)
	}
	reuseAccessBearer := reuseAccessToken.bearer
	reuseRefreshBearer := reuseRefreshToken.bearer
	if reuseAccessBearer == newAccessBearer || reuseRefreshBearer == newRefreshBearer {
		t.Fatal("different refresh idempotency keys derived the same replacement pair")
	}
	reuseAccessDigest := identitySessionHMAC(sessionKey, reuseAccessBearer)
	reuseRefreshDigest := identitySessionHMAC(sessionKey, reuseRefreshBearer)
	reuseIdempotencyDigest, _ := store.sessionTokens.digestActive(
		"identity-refresh-idempotency",
		browserSessionProjectID,
		browserSessionAccountID,
		reuseIdempotencyKey,
	)
	reuseRequestDigest, _ := store.sessionTokens.digestActive(
		"identity-refresh-request",
		browserSessionProjectID,
		browserSessionAccountID,
		oldRefreshDigest,
		reuseAccessDigest,
		reuseRefreshDigest,
	)
	expectIdentitySessionRefreshTransaction(mock)
	mock.ExpectQuery("FROM a1_rotate_identity_session_refresh_from_digest").
		WithArgs(
			browserSessionProjectID,
			browserSessionAccountID,
			oldRefreshDigest,
			reuseAccessDigest,
			reuseRefreshDigest,
			replayRequestedAccessExpiresAt,
			reuseIdempotencyDigest,
			reuseRequestDigest,
			`{"source":"go_identity_session_refresh_http"}`,
		).
		WillReturnRows(sqlmock.NewRows([]string{
			"session_id", "organization_id", "project_id", "principal_id",
			"rotation_generation", "outcome_code", "affected_count",
			"access_expires_at", "refresh_expires_at",
		}).AddRow(
			nil,
			browserSessionOrganizationID,
			browserSessionProjectID,
			browserSessionAccountID,
			0,
			"refresh_reuse_detected",
			2,
			requestedAccessExpiresAt,
			refreshExpiresAt,
		))
	mock.ExpectRollback()
	reuseRequest := browserRefreshRequest(oldAccess, oldRefresh, reuseIdempotencyKey)
	reuseResponse := httptest.NewRecorder()
	handler.ServeHTTP(reuseResponse, reuseRequest)
	if reuseResponse.Code != http.StatusConflict ||
		!strings.Contains(reuseResponse.Body.String(), `"identity_session_refresh_reused"`) {
		t.Fatalf("old refresh reuse was not rejected: %d %s", reuseResponse.Code, reuseResponse.Body.String())
	}
	for _, cookie := range reuseResponse.Result().Cookies() {
		if (cookie.Name == IdentitySessionCookieName || cookie.Name == IdentityRefreshCookieName) &&
			cookie.MaxAge != -1 {
			t.Fatalf("reuse response did not clear stale cookie: %#v", cookie)
		}
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func browserRefreshRequest(
	accessCookie *http.Cookie,
	refreshCookie *http.Cookie,
	idempotencyKey string,
) *http.Request {
	request := httptest.NewRequest(
		http.MethodPost,
		"https://api.example.test/v1/projects/"+browserSessionProjectID+
			"/accounts/"+browserSessionAccountID+"/browser-sessions/refresh",
		nil,
	)
	request.Header.Set("Origin", "https://api.example.test")
	request.Header.Set("Sec-Fetch-Site", "same-origin")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request.AddCookie(accessCookie)
	request.AddCookie(refreshCookie)
	return request
}

func browserSessionColumns() []string {
	return []string{"account", "actor", "session", "tenant", "project", "user"}
}

func browserSessionRows(sessionID string) *sqlmock.Rows {
	return sqlmock.NewRows(browserSessionColumns()).AddRow(
		browserSessionAccountID,
		browserSessionAccountID,
		sessionID,
		browserSessionOrganizationID,
		browserSessionProjectID,
		browserSessionAccountID,
	)
}

func expectIdentitySessionRefreshTransaction(mock sqlmock.Sqlmock) {
	mock.ExpectBegin()
	mock.ExpectExec("SELECT set_config").
		WithArgs("5000ms", "2000ms").
		WillReturnResult(sqlmock.NewResult(0, 1))
}

func cookiesByName(cookies []*http.Cookie) map[string]*http.Cookie {
	result := make(map[string]*http.Cookie, len(cookies))
	for _, cookie := range cookies {
		result[cookie.Name] = cookie
	}
	return result
}
