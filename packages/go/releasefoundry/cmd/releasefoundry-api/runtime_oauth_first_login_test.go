package main

import (
	"context"
	"database/sql"
	"fmt"
	"net/http"
	"strings"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
)

func productionOAuthFirstLoginTestEnv(t *testing.T) map[string]string {
	t.Helper()
	identityVault := productionIdentityDeliveryVaultTestEnv(t)
	return map[string]string{
		"RELEASEFOUNDRY_POSTGRES_DSN":                              "postgres://production-oauth.invalid/releasefoundry",
		"RELEASEFOUNDRY_IDENTITY_SESSION_HMAC_ACTIVE_VERSION":      "v1",
		"RELEASEFOUNDRY_IDENTITY_SESSION_HMAC_KEY":                 strings.Repeat("S", 40),
		"RELEASEFOUNDRY_IDENTITY_SESSION_HMAC_LEGACY_VERSION":      "v1",
		"RELEASEFOUNDRY_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION": "v1",
		"RELEASEFOUNDRY_IDENTITY_LIFECYCLE_RECEIPT_KEY":            strings.Repeat("L", 40),
		"RELEASEFOUNDRY_IDENTITY_BROWSER_INTENT_KEY":               strings.Repeat("I", 40),
		"RELEASEFOUNDRY_OAUTH_FIRST_LOGIN_ORGANIZATION_ID":         "11111111-1111-4111-8111-111111111111",
		"RELEASEFOUNDRY_OAUTH_FIRST_LOGIN_PROJECT_ID":              "22222222-2222-4222-8222-222222222222",
		"RELEASEFOUNDRY_OAUTH_VAULT_PUT_URL":                       "https://oauth-vault.example.test/v1/put",
		"RELEASEFOUNDRY_OAUTH_VAULT_GET_URL":                       "https://oauth-vault.example.test/v1/get",
		"RELEASEFOUNDRY_OAUTH_VAULT_BINDING_URL":                   "https://oauth-vault.example.test/v1/binding",
		"RELEASEFOUNDRY_OAUTH_VAULT_DELETE_URL":                    "https://oauth-vault.example.test/v1/delete",
		"RELEASEFOUNDRY_OAUTH_VAULT_MTLS_CA_FILE":                  identityVault["RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE"],
		"RELEASEFOUNDRY_OAUTH_VAULT_MTLS_CLIENT_CERT_FILE":         identityVault["RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE"],
		"RELEASEFOUNDRY_OAUTH_VAULT_MTLS_CLIENT_KEY_FILE":          identityVault["RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE"],
		"RELEASEFOUNDRY_OAUTH_VAULT_MTLS_SERVER_NAME":              "oauth-vault.example.test",
		"RELEASEFOUNDRY_GOOGLE_OAUTH_ENABLED":                      "true",
		"RELEASEFOUNDRY_GOOGLE_OAUTH_CLIENT_ID_REF":                "vault:oauth/google-client-id",
		"RELEASEFOUNDRY_GOOGLE_OAUTH_CLIENT_SECRET_REF":            "vault:oauth/google-client-secret",
		"RELEASEFOUNDRY_GOOGLE_OAUTH_CALLBACK_URL":                 "https://api.example.test/v1/identity/oauth/google/callback",
		"RELEASEFOUNDRY_GITHUB_OAUTH_ENABLED":                      "true",
		"RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_ID_REF":                "vault:oauth/github-client-id",
		"RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_SECRET_REF":            "vault:oauth/github-client-secret",
		"RELEASEFOUNDRY_GITHUB_OAUTH_CALLBACK_URL":                 "https://api.example.test/v1/identity/oauth/github/callback",
	}
}

type productionOAuthFixtureCredentials struct {
	values map[string]releasefoundry.OAuthClientCredentials
}

func (provider productionOAuthFixtureCredentials) OAuthCredentials(
	_ context.Context,
	providerName string,
) (releasefoundry.OAuthClientCredentials, error) {
	credentials, ok := provider.values[providerName]
	if !ok {
		return releasefoundry.OAuthClientCredentials{}, fmt.Errorf("fixture credentials unavailable")
	}
	return credentials, nil
}

type productionOAuthRecordingCredentials struct {
	calls  []string
	values map[string]releasefoundry.OAuthClientCredentials
}

func (provider *productionOAuthRecordingCredentials) OAuthCredentials(
	_ context.Context,
	providerName string,
) (releasefoundry.OAuthClientCredentials, error) {
	provider.calls = append(provider.calls, providerName)
	credentials, ok := provider.values[providerName]
	if !ok {
		return releasefoundry.OAuthClientCredentials{}, fmt.Errorf("fixture credentials unavailable")
	}
	return credentials, nil
}

func useProductionOAuthFixtureCredentials(t *testing.T) {
	t.Helper()
	original := productionOAuthCredentialsRuntimeFactory
	productionOAuthCredentialsRuntimeFactory = func(
		_ func(string) (string, bool),
		googleEnabled bool,
		githubEnabled bool,
		references map[string]releasefoundry.OAuthCredentialReference,
	) (*productionOAuthCredentialsRuntime, error) {
		if len(references) != 2 || !googleEnabled || !githubEnabled {
			return nil, fmt.Errorf("fixture OAuth credential graph is incomplete")
		}
		return &productionOAuthCredentialsRuntime{
			provider: productionOAuthFixtureCredentials{
				values: map[string]releasefoundry.OAuthClientCredentials{
					"google": {ClientID: "google-client-fixture", ClientSecret: "google-secret-fixture"},
					"github": {ClientID: "github-client-fixture", ClientSecret: "github-secret-fixture"},
				},
			},
		}, nil
	}
	t.Cleanup(func() { productionOAuthCredentialsRuntimeFactory = original })
}

func TestProductionIdentityRuntimeWiresCompletePublicOAuthFirstLoginGraph(t *testing.T) {
	useProductionOAuthFixtureCredentials(t)
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
		"vault":        func(values map[string]string) { delete(values, "RELEASEFOUNDRY_OAUTH_VAULT_PUT_URL") },
		"organization": func(values map[string]string) { delete(values, "RELEASEFOUNDRY_OAUTH_FIRST_LOGIN_ORGANIZATION_ID") },
		"callback": func(values map[string]string) {
			values["RELEASEFOUNDRY_GITHUB_OAUTH_CALLBACK_URL"] = "http://api.example.test/v1/identity/oauth/github/callback"
		},
		"credentials": func(values map[string]string) { delete(values, "RELEASEFOUNDRY_GOOGLE_OAUTH_CLIENT_SECRET_REF") },
		"intent key":  func(values map[string]string) { delete(values, "RELEASEFOUNDRY_IDENTITY_BROWSER_INTENT_KEY") },
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

func TestProductionOAuthCredentialReferencesRejectRawSecretsAndReuse(t *testing.T) {
	base := productionOAuthFirstLoginTestEnv(t)
	for name, mutate := range map[string]func(map[string]string){
		"raw client id": func(values map[string]string) {
			values["RELEASEFOUNDRY_GOOGLE_OAUTH_CLIENT_ID"] = "legacy-client-material"
		},
		"raw client secret": func(values map[string]string) {
			values["RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_SECRET"] = "legacy-secret-material"
		},
		"shared reference": func(values map[string]string) {
			values["RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_ID_REF"] = values["RELEASEFOUNDRY_GOOGLE_OAUTH_CLIENT_ID_REF"]
		},
		"same provider references": func(values map[string]string) {
			values["RELEASEFOUNDRY_GOOGLE_OAUTH_CLIENT_SECRET_REF"] = values["RELEASEFOUNDRY_GOOGLE_OAUTH_CLIENT_ID_REF"]
		},
	} {
		t.Run(name, func(t *testing.T) {
			values := cloneStrings(base)
			mutate(values)
			_, err := productionOAuthCredentialReferencesFromEnv(
				lookup(values), true, true,
			)
			if err == nil {
				t.Fatal("unsafe production OAuth credential configuration was accepted")
			}
			assertErrorOmitsValues(t, err, values)
		})
	}
	values := cloneStrings(base)
	delete(values, "RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_ID_REF")
	delete(values, "RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_SECRET_REF")
	references, err := productionOAuthCredentialReferencesFromEnv(
		lookup(values), true, false,
	)
	if err != nil || len(references) != 1 || references["google"].ClientIDRef == "" {
		t.Fatalf("disabled provider incorrectly required references: %#v %v", references, err)
	}
}

func TestProductionOAuthRuntimeRejectsSharedResolvedClientMaterial(t *testing.T) {
	base := productionOAuthFirstLoginTestEnv(t)
	original := productionOAuthCredentialsRuntimeFactory
	productionOAuthCredentialsRuntimeFactory = func(
		_ func(string) (string, bool),
		googleEnabled bool,
		githubEnabled bool,
		_ map[string]releasefoundry.OAuthCredentialReference,
	) (*productionOAuthCredentialsRuntime, error) {
		return &productionOAuthCredentialsRuntime{
			provider: productionOAuthFixtureCredentials{
				values: map[string]releasefoundry.OAuthClientCredentials{
					"google": {ClientID: "shared-client-fixture", ClientSecret: "google-secret-fixture"},
					"github": {ClientID: "shared-client-fixture", ClientSecret: "github-secret-fixture"},
				},
			},
		}, nil
	}
	t.Cleanup(func() { productionOAuthCredentialsRuntimeFactory = original })
	_, err := productionOAuthFirstLoginDependenciesFromEnv(lookup(base))
	if err == nil || !strings.Contains(err.Error(), "must not share") {
		t.Fatalf("shared resolved OAuth client material was accepted: %v", err)
	}
}

func TestProductionOAuthRuntimeDoesNotResolveDisabledProvider(t *testing.T) {
	values := productionOAuthFirstLoginTestEnv(t)
	values["RELEASEFOUNDRY_GITHUB_OAUTH_ENABLED"] = "false"
	delete(values, "RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_ID_REF")
	delete(values, "RELEASEFOUNDRY_GITHUB_OAUTH_CLIENT_SECRET_REF")
	delete(values, "RELEASEFOUNDRY_GITHUB_OAUTH_CALLBACK_URL")
	recorder := &productionOAuthRecordingCredentials{
		values: map[string]releasefoundry.OAuthClientCredentials{
			"google": {
				ClientID:     "google-client-fixture",
				ClientSecret: "google-secret-fixture",
			},
		},
	}
	original := productionOAuthCredentialsRuntimeFactory
	productionOAuthCredentialsRuntimeFactory = func(
		_ func(string) (string, bool),
		googleEnabled bool,
		githubEnabled bool,
		references map[string]releasefoundry.OAuthCredentialReference,
	) (*productionOAuthCredentialsRuntime, error) {
		if !googleEnabled || githubEnabled || len(references) != 1 {
			return nil, fmt.Errorf("disabled provider entered the credential resolver graph")
		}
		return &productionOAuthCredentialsRuntime{provider: recorder}, nil
	}
	t.Cleanup(func() { productionOAuthCredentialsRuntimeFactory = original })
	dependencies, err := productionOAuthFirstLoginDependenciesFromEnv(lookup(values))
	if err != nil {
		t.Fatal(err)
	}
	defer dependencies.close()
	if len(recorder.calls) != 1 || recorder.calls[0] != "google" {
		t.Fatalf("disabled provider was resolved: %#v", recorder.calls)
	}
	if _, exists := dependencies.providers["github"]; exists {
		t.Fatal("disabled provider entered the public first-login graph")
	}
}

func TestProductionOAuthCredentialsRuntimeBuildsCompleteMTLSResolver(t *testing.T) {
	identityVault := productionIdentityDeliveryVaultTestEnv(t)
	values := map[string]string{
		"RELEASEFOUNDRY_OAUTH_CREDENTIALS_RESOLVE_URL":           "https://credential-resolver.example.test/v1/oauth/resolve",
		"RELEASEFOUNDRY_OAUTH_CREDENTIALS_MTLS_CA_FILE":          identityVault["RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE"],
		"RELEASEFOUNDRY_OAUTH_CREDENTIALS_MTLS_CLIENT_CERT_FILE": identityVault["RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE"],
		"RELEASEFOUNDRY_OAUTH_CREDENTIALS_MTLS_CLIENT_KEY_FILE":  identityVault["RELEASEFOUNDRY_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE"],
		"RELEASEFOUNDRY_OAUTH_CREDENTIALS_MTLS_SERVER_NAME":      "credential-resolver.example.test",
	}
	references := map[string]releasefoundry.OAuthCredentialReference{
		"google": {
			ClientIDRef:     "vault:oauth/google-client-id",
			ClientSecretRef: "vault:oauth/google-client-secret",
		},
		"github": {
			ClientIDRef:     "vault:oauth/github-client-id",
			ClientSecretRef: "vault:oauth/github-client-secret",
		},
	}
	runtime, err := productionOAuthCredentialsRuntimeFromEnv(
		lookup(values), true, true, references,
	)
	if err != nil {
		t.Fatal(err)
	}
	defer runtime.close()
	if runtime.provider == nil || runtime.client == nil {
		t.Fatal("production credential resolver runtime is incomplete")
	}
	transport, ok := runtime.client.Transport.(*http.Transport)
	if !ok || transport.TLSClientConfig == nil {
		t.Fatalf("production credential resolver did not use the mTLS transport: %T", runtime.client.Transport)
	}
	if transport.TLSClientConfig.ServerName != values["RELEASEFOUNDRY_OAUTH_CREDENTIALS_MTLS_SERVER_NAME"] ||
		transport.TLSClientConfig.RootCAs == nil ||
		len(transport.TLSClientConfig.Certificates) != 1 ||
		runtime.client.Timeout != productionIdentityDeliveryVaultRequestTimeout {
		t.Fatal("production credential resolver lost its trust, identity, server name, or timeout binding")
	}

	for missing := range values {
		t.Run("missing "+missing, func(t *testing.T) {
			incomplete := cloneStrings(values)
			delete(incomplete, missing)
			resolver, err := productionOAuthCredentialsRuntimeFromEnv(
				lookup(incomplete), true, true, references,
			)
			if resolver != nil || err == nil {
				t.Fatal("incomplete production credential resolver configuration was accepted")
			}
			assertErrorOmitsValues(t, err, values)
		})
	}
}

func TestProductionIdentityRuntimeRejectsLocalhostOAuthSessionFlags(t *testing.T) {
	for _, key := range []string{"RELEASEFOUNDRY_GOOGLE_OAUTH_DEV_SESSION_ENABLED", "RELEASEFOUNDRY_GITHUB_OAUTH_DEV_SESSION_ENABLED"} {
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
		"RELEASEFOUNDRY_IDENTITY_BROWSER_INTENT_KEY":    strings.Repeat("I", 40),
		"RELEASEFOUNDRY_IDENTITY_VERIFICATION_HMAC_KEY": "too-short-legacy-fallback",
	}))
	if err != nil || transport == nil {
		t.Fatalf("dedicated browser intent key was not preferred: %v", err)
	}
}
