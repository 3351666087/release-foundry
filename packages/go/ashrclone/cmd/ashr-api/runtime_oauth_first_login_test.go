package main

import (
	"context"
	"database/sql"
	"strings"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
)

func productionOAuthFirstLoginTestEnv(t *testing.T) map[string]string {
	t.Helper()
	identityVault := productionIdentityDeliveryVaultTestEnv(t)
	return map[string]string{
		"ASHR_POSTGRES_DSN":                              "postgres://production-oauth.invalid/ashr",
		"ASHR_IDENTITY_SESSION_HMAC_ACTIVE_VERSION":      "v1",
		"ASHR_IDENTITY_SESSION_HMAC_KEY":                 strings.Repeat("S", 40),
		"ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION":      "v1",
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION": "v1",
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY":            strings.Repeat("L", 40),
		"ASHR_IDENTITY_BROWSER_INTENT_KEY":               strings.Repeat("I", 40),
		"ASHR_OAUTH_FIRST_LOGIN_ORGANIZATION_ID":         "11111111-1111-4111-8111-111111111111",
		"ASHR_OAUTH_FIRST_LOGIN_PROJECT_ID":              "22222222-2222-4222-8222-222222222222",
		"ASHR_OAUTH_VAULT_PUT_URL":                       "https://oauth-vault.example.test/v1/put",
		"ASHR_OAUTH_VAULT_GET_URL":                       "https://oauth-vault.example.test/v1/get",
		"ASHR_OAUTH_VAULT_BINDING_URL":                   "https://oauth-vault.example.test/v1/binding",
		"ASHR_OAUTH_VAULT_DELETE_URL":                    "https://oauth-vault.example.test/v1/delete",
		"ASHR_OAUTH_VAULT_MTLS_CA_FILE":                  identityVault["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE"],
		"ASHR_OAUTH_VAULT_MTLS_CLIENT_CERT_FILE":         identityVault["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE"],
		"ASHR_OAUTH_VAULT_MTLS_CLIENT_KEY_FILE":          identityVault["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE"],
		"ASHR_OAUTH_VAULT_MTLS_SERVER_NAME":              "oauth-vault.example.test",
		"ASHR_GOOGLE_OAUTH_ENABLED":                      "true",
		"ASHR_GOOGLE_OAUTH_CLIENT_ID":                    "google-client-fixture",
		"ASHR_GOOGLE_OAUTH_CLIENT_SECRET":                "google-secret-fixture",
		"ASHR_GOOGLE_OAUTH_CALLBACK_URL":                 "https://api.example.test/v1/identity/oauth/google/callback",
		"ASHR_GITHUB_OAUTH_ENABLED":                      "true",
		"ASHR_GITHUB_OAUTH_CLIENT_ID":                    "github-client-fixture",
		"ASHR_GITHUB_OAUTH_CLIENT_SECRET":                "github-secret-fixture",
		"ASHR_GITHUB_OAUTH_CALLBACK_URL":                 "https://api.example.test/v1/identity/oauth/github/callback",
	}
}

func TestProductionIdentityRuntimeWiresCompletePublicOAuthFirstLoginGraph(t *testing.T) {
	db, mock, err := sqlmock.New(sqlmock.MonitorPingsOption(true))
	if err != nil {
		t.Fatal(err)
	}
	originalOpen := openIdentityDatabase
	openIdentityDatabase = func(driverName, dataSourceName string) (*sql.DB, error) {
		return db, nil
	}
	t.Cleanup(func() { openIdentityDatabase = originalOpen })
	mock.ExpectPing()
	mock.ExpectQuery("SELECT to_regclass").WillReturnRows(sqlmock.NewRows([]string{"ready"}).AddRow(true))
	runtime, err := newIdentityRuntimeFromEnv(context.Background(), lookup(productionOAuthFirstLoginTestEnv(t)))
	if err != nil {
		t.Fatal(err)
	}
	defer runtime.close()
	if len(runtime.oauthFirstLogins) != 2 || runtime.oauthFirstLogins["google"] == nil || runtime.oauthFirstLogins["github"] == nil {
		t.Fatalf("production OAuth first-login providers were not fully wired: %#v", runtime.oauthFirstLogins)
	}
	capabilities := runtime.identityLifecycle.ProviderCapabilities()
	enabled := map[string]bool{}
	for _, capability := range capabilities {
		enabled[string(capability.Provider)] = capability.Enabled
	}
	if !enabled["google"] || !enabled["github"] {
		t.Fatalf("production lifecycle did not expose configured OAuth capabilities: %#v", capabilities)
	}
	if runtime.sessionReceiptTransport == nil {
		t.Fatal("production OAuth first-login omitted session/cookie handoff transport")
	}
	options := identityHTTPServerOptions(runtime, runtime.identitySessions)
	if len(options.OAuthFirstLogins) != 2 || options.OAuthFirstLoginIntents == nil || options.IdentitySessionReceiptTransport == nil {
		t.Fatalf("production HTTP server omitted OAuth first-login dependencies: %#v", options)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentityRuntimeOAuthFailsClosedBeforeDatabaseReadiness(t *testing.T) {
	base := productionOAuthFirstLoginTestEnv(t)
	for name, mutate := range map[string]func(map[string]string){
		"vault":        func(values map[string]string) { delete(values, "ASHR_OAUTH_VAULT_PUT_URL") },
		"organization": func(values map[string]string) { delete(values, "ASHR_OAUTH_FIRST_LOGIN_ORGANIZATION_ID") },
		"callback": func(values map[string]string) {
			values["ASHR_GITHUB_OAUTH_CALLBACK_URL"] = "http://api.example.test/v1/identity/oauth/github/callback"
		},
		"credentials": func(values map[string]string) { delete(values, "ASHR_GOOGLE_OAUTH_CLIENT_SECRET") },
		"intent key":  func(values map[string]string) { delete(values, "ASHR_IDENTITY_BROWSER_INTENT_KEY") },
	} {
		t.Run(name, func(t *testing.T) {
			values := cloneStrings(base)
			mutate(values)
			_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(values))
			if err == nil {
				t.Fatal("incomplete production OAuth first-login capability was accepted")
			}
			assertErrorOmitsValues(t, err, values)
		})
	}
}

func TestProductionIdentityRuntimeRejectsLocalhostOAuthSessionFlags(t *testing.T) {
	for _, key := range []string{"ASHR_GOOGLE_OAUTH_DEV_SESSION_ENABLED", "ASHR_GITHUB_OAUTH_DEV_SESSION_ENABLED"} {
		values := productionOAuthFirstLoginTestEnv(t)
		values[key] = "true"
		_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(values))
		if err == nil || !strings.Contains(strings.ToLower(err.Error()), "development") {
			t.Fatalf("production runtime accepted %s: %v", key, err)
		}
	}
}

func TestProductionIdentityRuntimeOAuthDisabledDoesNotExposePublicProviders(t *testing.T) {
	runtime := identityRuntime{}
	options := identityHTTPServerOptions(runtime, nil)
	if len(options.OAuthFirstLogins) != 0 || options.OAuthFirstLoginIntents != nil {
		t.Fatalf("disabled production OAuth exposed a public provider route: %#v", options)
	}
}

func TestProductionIdentitySessionCookieTransportPrefersDedicatedBrowserIntentKey(t *testing.T) {
	transport, err := productionIdentitySessionReceiptTransportFromEnv(lookup(map[string]string{
		"ASHR_IDENTITY_BROWSER_INTENT_KEY":    strings.Repeat("I", 40),
		"ASHR_IDENTITY_VERIFICATION_HMAC_KEY": "too-short-legacy-fallback",
	}))
	if err != nil || transport == nil {
		t.Fatalf("dedicated browser intent key was not preferred: %v", err)
	}
}
