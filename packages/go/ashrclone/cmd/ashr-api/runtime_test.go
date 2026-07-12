package main

import (
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/ashr-labs/ashr/packages/go/ashrclone"
)

func lookup(values map[string]string) func(string) (string, bool) {
	return func(key string) (string, bool) {
		value, ok := values[key]
		return value, ok
	}
}

func TestIdentityRuntimeDefaultsToPostgresAndFailsClosedWithoutDSN(t *testing.T) {
	_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(map[string]string{}))
	if err == nil || !strings.Contains(err.Error(), "ASHR_POSTGRES_DSN") {
		t.Fatalf("expected missing postgres DSN error, got %v", err)
	}
}

func TestIdentityRuntimeMemoryRequiresExplicitDevelopmentOptIn(t *testing.T) {
	for _, values := range []map[string]string{
		{"ASHR_IDENTITY_RUNTIME": "memory"},
		{"ASHR_IDENTITY_RUNTIME": "memory", "ASHR_ENVIRONMENT": "production", "ASHR_IDENTITY_MEMORY_ENABLED": "true"},
		{"ASHR_IDENTITY_RUNTIME": "memory", "ASHR_ENVIRONMENT": "development"},
	} {
		if _, err := newIdentityRuntimeFromEnv(context.Background(), lookup(values)); err == nil {
			t.Fatalf("expected memory configuration to fail: %#v", values)
		}
	}
	runtime, err := newIdentityRuntimeFromEnv(context.Background(), lookup(map[string]string{
		"ASHR_IDENTITY_RUNTIME":        "memory",
		"ASHR_ENVIRONMENT":             "development",
		"ASHR_IDENTITY_MEMORY_ENABLED": "true",
	}))
	if err != nil {
		t.Fatal(err)
	}
	if runtime.mode != ashrclone.IdentityRuntimeMemory || runtime.unifiedIdentity == nil {
		t.Fatalf("unexpected memory runtime: %#v", runtime)
	}
}

func TestIdentityRuntimeRejectsUnknownMode(t *testing.T) {
	_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(map[string]string{
		"ASHR_IDENTITY_RUNTIME": "automatic",
	}))
	if err == nil || !strings.Contains(err.Error(), "unsupported") {
		t.Fatalf("expected unsupported mode error, got %v", err)
	}
}

func TestIdentityRuntimeVerificationRequiresExplicitDevelopmentMemoryAndKey(t *testing.T) {
	base := map[string]string{
		"ASHR_IDENTITY_RUNTIME":              "memory",
		"ASHR_ENVIRONMENT":                   "development",
		"ASHR_IDENTITY_MEMORY_ENABLED":       "true",
		"ASHR_IDENTITY_VERIFICATION_ENABLED": "true",
	}
	if _, err := newIdentityRuntimeFromEnv(context.Background(), lookup(base)); err == nil {
		t.Fatal("verification started without explicit memory sender/store and digest key")
	}
	base["ASHR_IDENTITY_VERIFICATION_MEMORY_ENABLED"] = "true"
	if _, err := newIdentityRuntimeFromEnv(context.Background(), lookup(base)); err == nil {
		t.Fatal("verification started without digest key")
	}
	base["ASHR_IDENTITY_VERIFICATION_HMAC_KEY"] = "development-verification-key-32-bytes"
	runtime, err := newIdentityRuntimeFromEnv(context.Background(), lookup(base))
	if err != nil {
		t.Fatal(err)
	}
	if runtime.verification == nil || runtime.close == nil {
		t.Fatalf("development verification runtime was not wired: %#v", runtime)
	}
	if err := runtime.close(); err != nil {
		t.Fatal(err)
	}
}

func TestIdentityRuntimeVerificationUsesMemorySenderUnlessSMTPExplicitlyEnabled(t *testing.T) {
	sender, err := developmentIdentityVerificationSenderFromEnv(lookup(map[string]string{
		"ASHR_SMTP_HOST":      "ignored.example.test",
		"ASHR_SMTP_PORT":      "not-a-port",
		"ASHR_SMTP_FROM":      "ignored@example.test",
		"ASHR_SMTP_AUTH_CODE": "ignored-secret",
	}))
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := sender.(*ashrclone.MemoryIdentityVerificationSender); !ok {
		t.Fatalf("SMTP was not enabled, got sender %T", sender)
	}
}

func TestIdentityRuntimeVerificationSMTPRequiresCompleteConfiguration(t *testing.T) {
	base := map[string]string{
		"ASHR_IDENTITY_VERIFICATION_SMTP_ENABLED": "true",
		"ASHR_SMTP_HOST":      "host-value-must-not-leak.example.test",
		"ASHR_SMTP_PORT":      "2465",
		"ASHR_SMTP_FROM":      "from-value-must-not-leak@example.test",
		"ASHR_SMTP_AUTH_CODE": "auth-value-must-not-leak",
	}
	for _, missing := range []string{"ASHR_SMTP_HOST", "ASHR_SMTP_PORT", "ASHR_SMTP_FROM", "ASHR_SMTP_AUTH_CODE"} {
		values := cloneStrings(base)
		delete(values, missing)
		_, err := developmentIdentityVerificationSenderFromEnv(lookup(values))
		if err == nil {
			t.Fatalf("SMTP sender started without %s", missing)
		}
		if !strings.Contains(err.Error(), missing) {
			t.Fatalf("missing configuration error did not identify %s: %v", missing, err)
		}
		assertErrorOmitsValues(t, err, base)
	}
}

func TestIdentityRuntimeVerificationSMTPRejectsInvalidPortWithoutLeakingValue(t *testing.T) {
	const invalidPort = "invalid-port-secret"
	_, err := developmentIdentityVerificationSenderFromEnv(lookup(map[string]string{
		"ASHR_IDENTITY_VERIFICATION_SMTP_ENABLED": "true",
		"ASHR_SMTP_HOST":      "smtp.example.test",
		"ASHR_SMTP_PORT":      invalidPort,
		"ASHR_SMTP_FROM":      "verify@example.test",
		"ASHR_SMTP_AUTH_CODE": "auth-code-secret",
	}))
	if err == nil || !strings.Contains(err.Error(), "ASHR_SMTP_PORT") {
		t.Fatalf("expected invalid SMTP port error, got %v", err)
	}
	assertErrorOmitsValues(t, err, map[string]string{
		"host": "smtp.example.test", "port": invalidPort,
		"from": "verify@example.test", "auth": "auth-code-secret",
	})
}

func TestIdentityRuntimeVerificationSMTPRedactsInvalidSenderConfiguration(t *testing.T) {
	base := map[string]string{
		"ASHR_IDENTITY_VERIFICATION_SMTP_ENABLED": "true",
		"ASHR_SMTP_HOST":      "smtp.example.test",
		"ASHR_SMTP_PORT":      "465",
		"ASHR_SMTP_FROM":      "verify@example.test",
		"ASHR_SMTP_AUTH_CODE": "auth-code-secret",
	}
	for name, mutate := range map[string]func(map[string]string){
		"host": func(values map[string]string) {
			values["ASHR_SMTP_HOST"] = "host-value-must-not-leak.example.test\r\nunsafe"
		},
		"from": func(values map[string]string) {
			values["ASHR_SMTP_FROM"] = "from-value-must-not-leak"
		},
		"auth": func(values map[string]string) {
			values["ASHR_SMTP_AUTH_CODE"] = "auth-value-must-not-leak\r\nunsafe"
		},
	} {
		t.Run(name, func(t *testing.T) {
			values := cloneStrings(base)
			mutate(values)
			_, err := developmentIdentityVerificationSenderFromEnv(lookup(values))
			if err == nil {
				t.Fatal("invalid SMTP sender configuration was accepted")
			}
			assertErrorOmitsValues(t, err, values)
		})
	}
}

func TestIdentityRuntimeVerificationSMTPWiresConfiguredSender(t *testing.T) {
	base := map[string]string{
		"ASHR_IDENTITY_RUNTIME":                     "memory",
		"ASHR_ENVIRONMENT":                          "development",
		"ASHR_IDENTITY_MEMORY_ENABLED":              "true",
		"ASHR_IDENTITY_VERIFICATION_ENABLED":        "true",
		"ASHR_IDENTITY_VERIFICATION_MEMORY_ENABLED": "true",
		"ASHR_IDENTITY_VERIFICATION_SMTP_ENABLED":   "true",
		"ASHR_IDENTITY_VERIFICATION_HMAC_KEY":       "development-verification-key-32-bytes",
		"ASHR_SMTP_HOST":                            "smtp.example.test",
		"ASHR_SMTP_PORT":                            "465",
		"ASHR_SMTP_FROM":                            "verify@example.test",
		"ASHR_SMTP_AUTH_CODE":                       "development-auth-code",
	}
	runtime, err := newIdentityRuntimeFromEnv(context.Background(), lookup(base))
	if err != nil {
		t.Fatal(err)
	}
	if runtime.verification == nil || runtime.close == nil {
		t.Fatalf("development SMTP verification runtime was not wired: %#v", runtime)
	}
	if err := runtime.close(); err != nil {
		t.Fatal(err)
	}
}

func TestProductionIdentityRuntimeRefusesMemoryVerification(t *testing.T) {
	_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(map[string]string{
		"ASHR_IDENTITY_RUNTIME":              "postgres",
		"ASHR_IDENTITY_VERIFICATION_ENABLED": "true",
	}))
	if err == nil || !strings.Contains(err.Error(), "ASHR_POSTGRES_DSN or DATABASE_URL") {
		t.Fatalf("production verification did not fail closed: %v", err)
	}
}

func TestProductionIdentityDeliveryVaultFromEnvBuildsMTLSSealerAndDeleter(t *testing.T) {
	values := productionIdentityDeliveryVaultTestEnv(t)
	vault, err := productionIdentityDeliveryVaultFromEnv(lookup(values))
	if err != nil {
		t.Fatal(err)
	}
	defer vault.close()
	if vault.sealer == nil || vault.client == nil {
		t.Fatalf("production delivery vault was not fully constructed: %#v", vault)
	}
	var sealer ashrclone.IdentityDeliveryVaultSealer = vault.sealer
	var deleter ashrclone.IdentityDeliveryVaultDeleter = vault.sealer
	if sealer == nil || deleter == nil {
		t.Fatal("production delivery vault did not implement both lifecycle operations")
	}
	transport, ok := vault.client.Transport.(*http.Transport)
	if !ok || transport.TLSClientConfig == nil {
		t.Fatalf("production delivery vault did not use the mTLS transport: %T", vault.client.Transport)
	}
	if transport.TLSClientConfig.ServerName != values["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_SERVER_NAME"] ||
		transport.TLSClientConfig.RootCAs == nil ||
		len(transport.TLSClientConfig.Certificates) != 1 ||
		vault.client.Timeout != productionIdentityDeliveryVaultRequestTimeout {
		t.Fatal("production delivery vault lost its trust, identity, server name, or timeout binding")
	}
}

func TestProductionIdentityDeliveryVaultConfigIsAllOrNoneAndRedacted(t *testing.T) {
	base := productionIdentityDeliveryVaultTestEnv(t)
	keys := []string{
		"ASHR_IDENTITY_DELIVERY_VAULT_SEAL_URL",
		"ASHR_IDENTITY_DELIVERY_VAULT_DELETE_URL",
		"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE",
		"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE",
		"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE",
		"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_SERVER_NAME",
	}
	for _, missing := range keys {
		t.Run(missing, func(t *testing.T) {
			values := cloneStrings(base)
			delete(values, missing)
			_, err := productionIdentityDeliveryVaultConfigFromEnv(lookup(values))
			if err == nil || !strings.Contains(err.Error(), missing) ||
				!strings.Contains(err.Error(), "all-or-none") {
				t.Fatalf("partial vault configuration was accepted: %v", err)
			}
			assertErrorOmitsValues(t, err, values)
		})
	}

	values := cloneStrings(base)
	unsafeValue := values["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE"] + "\r\nprivate-path"
	values["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE"] = unsafeValue
	_, err := productionIdentityDeliveryVaultConfigFromEnv(lookup(values))
	if err == nil || strings.Contains(err.Error(), unsafeValue) {
		t.Fatalf("unsafe vault configuration was accepted or echoed: %v", err)
	}
}

func TestProductionIdentityDeliveryVaultPEMReadIsBoundedAndPathSafe(t *testing.T) {
	tempDirectory := t.TempDir()
	emptyPath := filepath.Join(tempDirectory, "empty-secret.pem")
	if err := os.WriteFile(emptyPath, nil, 0o600); err != nil {
		t.Fatal(err)
	}
	oversizedPath := filepath.Join(tempDirectory, "oversized-secret.pem")
	if err := os.WriteFile(oversizedPath, bytes.Repeat([]byte("S"), 33), 0o600); err != nil {
		t.Fatal(err)
	}
	missingPath := filepath.Join(tempDirectory, "missing-secret.pem")
	for _, test := range []struct {
		name  string
		path  string
		limit int64
	}{
		{name: "missing", path: missingPath, limit: 32},
		{name: "empty", path: emptyPath, limit: 32},
		{name: "directory", path: tempDirectory, limit: 32},
		{name: "oversized", path: oversizedPath, limit: 32},
	} {
		t.Run(test.name, func(t *testing.T) {
			encoded, err := readProductionIdentityDeliveryVaultPEM(test.path, test.limit)
			if err == nil || encoded != nil {
				t.Fatalf("unsafe credential file was accepted: bytes=%d err=%v", len(encoded), err)
			}
			if strings.Contains(err.Error(), test.path) || strings.Contains(err.Error(), "SSSS") {
				t.Fatalf("credential file error leaked path or material: %v", err)
			}
		})
	}
}

func TestProductionIdentityDeliveryVaultRejectsUnsafeInputsWithoutEcho(t *testing.T) {
	const privateMaterial = "private-key-material-that-must-not-leak"
	for _, test := range []struct {
		name   string
		mutate func(*testing.T, map[string]string)
	}{
		{
			name: "malformed private key",
			mutate: func(t *testing.T, values map[string]string) {
				t.Helper()
				if err := os.WriteFile(
					values["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE"],
					[]byte(privateMaterial),
					0o600,
				); err != nil {
					t.Fatal(err)
				}
			},
		},
		{
			name: "non TLS endpoint",
			mutate: func(_ *testing.T, values map[string]string) {
				values["ASHR_IDENTITY_DELIVERY_VAULT_SEAL_URL"] = "http://secret-vault.invalid/seal"
			},
		},
		{
			name: "invalid server name",
			mutate: func(_ *testing.T, values map[string]string) {
				values["ASHR_IDENTITY_DELIVERY_VAULT_MTLS_SERVER_NAME"] = "secret-vault.invalid/path"
			},
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			values := productionIdentityDeliveryVaultTestEnv(t)
			test.mutate(t, values)
			_, err := productionIdentityDeliveryVaultFromEnv(lookup(values))
			if err == nil {
				t.Fatal("unsafe production vault input was accepted")
			}
			assertErrorOmitsValues(t, err, values)
			if strings.Contains(err.Error(), privateMaterial) {
				t.Fatalf("vault startup error leaked private material: %v", err)
			}
		})
	}
}

func TestProductionIdentityVerificationRequiresVaultBeforeDatabaseAccess(t *testing.T) {
	const (
		dsnSecret       = "postgres://runtime-db-secret@database-must-not-be-contacted.invalid/ashr"
		keySecret       = "production-session-secret-that-must-not-leak"
		lifecycleSecret = "production-lifecycle-secret-that-must-not-leak"
	)
	_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(map[string]string{
		"ASHR_POSTGRES_DSN":                              dsnSecret,
		"ASHR_IDENTITY_SESSION_HMAC_ACTIVE_VERSION":      "v1",
		"ASHR_IDENTITY_SESSION_HMAC_KEY":                 keySecret,
		"ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION":      "v1",
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION": "v1",
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY":            lifecycleSecret,
		"ASHR_IDENTITY_VERIFICATION_ENABLED":             "true",
		"ASHR_IDENTITY_VERIFICATION_HMAC_KEY":            "production-verification-secret-must-not-leak",
	}))
	if err == nil || !strings.Contains(err.Error(), "ASHR_IDENTITY_DELIVERY_VAULT_SEAL_URL") ||
		!strings.Contains(err.Error(), "all-or-none") {
		t.Fatalf("production verification did not fail closed on its vault dependency: %v", err)
	}
	for _, secret := range []string{
		dsnSecret,
		keySecret,
		lifecycleSecret,
		"production-verification-secret-must-not-leak",
	} {
		if strings.Contains(err.Error(), secret) {
			t.Fatalf("production startup error leaked a secret: %v", err)
		}
	}
}

type recordingCloseIdleTransport struct {
	closed bool
}

func (*recordingCloseIdleTransport) RoundTrip(*http.Request) (*http.Response, error) {
	return nil, fmt.Errorf("unexpected request")
}

func (transport *recordingCloseIdleTransport) CloseIdleConnections() {
	transport.closed = true
}

func TestProductionIdentityDeliveryVaultRuntimeClosesIdleConnections(t *testing.T) {
	transport := &recordingCloseIdleTransport{}
	vault := &productionIdentityDeliveryVaultRuntime{
		client: &http.Client{Transport: transport},
	}
	vault.close()
	if !transport.closed {
		t.Fatal("production vault runtime left idle connections open")
	}
}

func TestIdentitySessionHMACRuntimeConfigSupportsRotationAndExplicitLegacy(t *testing.T) {
	activeKey := strings.Repeat("A", 40)
	previousV2 := strings.Repeat("B", 40)
	previousV1 := strings.Repeat("C", 40)
	config, err := identitySessionHMACRuntimeConfigFromEnv(lookup(map[string]string{
		"ASHR_IDENTITY_SESSION_HMAC_ACTIVE_VERSION": "v3",
		"ASHR_IDENTITY_SESSION_HMAC_KEY":            activeKey,
		"ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION": "v1",
		"ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON": fmt.Sprintf(
			`[{"version":"v2","key":%q,"retire_at":"2027-09-01T00:00:00Z"},{"version":"v1","key":%q,"retire_at":"2027-09-01T00:00:00Z"}]`,
			previousV2,
			previousV1,
		),
	}))
	if err != nil {
		t.Fatal(err)
	}
	if config.activeVersion != "v3" || string(config.activeKey) != activeKey ||
		config.legacyVersion != "v1" || len(config.previousKeys) != 2 ||
		config.previousKeys[0].Version != "v2" || string(config.previousKeys[0].Key) != previousV2 ||
		config.previousKeys[1].Version != "v1" || string(config.previousKeys[1].Key) != previousV1 {
		t.Fatalf("unexpected keyring config: active=%q legacy=%q previous=%d", config.activeVersion, config.legacyVersion, len(config.previousKeys))
	}
	activeBytes := config.activeKey
	previousBytes := config.previousKeys[0].Key
	config.clear()
	for _, value := range append(activeBytes, previousBytes...) {
		if value != 0 {
			t.Fatal("cleared keyring retained key bytes")
		}
	}
}

func TestIdentityLifecycleKeyRuntimeConfigSupportsRotationAndClearsKeys(t *testing.T) {
	activeKey := strings.Repeat("L", 40)
	previousV2 := strings.Repeat("M", 40)
	previousV1 := strings.Repeat("N", 40)
	config, err := identityLifecycleKeyRuntimeConfigFromEnv(lookup(map[string]string{
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION": "v3",
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY":            activeKey,
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON": fmt.Sprintf(
			`[{"version":"v2","key":%q},{"version":"v1","key":%q}]`,
			previousV2,
			previousV1,
		),
	}))
	if err != nil {
		t.Fatal(err)
	}
	if config.activeVersion != "v3" || string(config.activeKey) != activeKey ||
		len(config.previousKeys) != 2 ||
		config.previousKeys[0].Version != "v2" || string(config.previousKeys[0].Key) != previousV2 ||
		config.previousKeys[1].Version != "v1" || string(config.previousKeys[1].Key) != previousV1 {
		t.Fatalf("unexpected lifecycle keyring config: active=%q previous=%d", config.activeVersion, len(config.previousKeys))
	}
	activeBytes := config.activeKey
	previousV2Bytes := config.previousKeys[0].Key
	previousV1Bytes := config.previousKeys[1].Key
	config.clear()
	for _, key := range [][]byte{activeBytes, previousV2Bytes, previousV1Bytes} {
		for _, value := range key {
			if value != 0 {
				t.Fatal("cleared lifecycle keyring retained key bytes")
			}
		}
	}
	if config.activeKey != nil || config.previousKeys != nil || config.activeVersion != "" {
		t.Fatalf("cleared lifecycle keyring retained metadata: %#v", config)
	}
}

func TestIdentityLifecycleKeyRuntimeConfigRejectsUnsafeInputsWithoutEchoingKeys(t *testing.T) {
	activeSecret := "active-lifecycle-secret-that-must-not-leak-1234"
	previousSecret := "previous-lifecycle-secret-that-must-not-leak"
	base := map[string]string{
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION": "v2",
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY":            activeSecret,
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON": fmt.Sprintf(
			`[{"version":"v1","key":%q}]`,
			previousSecret,
		),
	}
	tests := []struct {
		name   string
		mutate func(map[string]string)
	}{
		{name: "missing active version", mutate: func(values map[string]string) {
			delete(values, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION")
		}},
		{name: "missing active key", mutate: func(values map[string]string) {
			delete(values, "ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY")
		}},
		{name: "invalid active version", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION"] = "../private-version"
		}},
		{name: "short active key", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY"] = "short-active-lifecycle-secret"
		}},
		{name: "duplicate active version", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON"] = fmt.Sprintf(
				`[{"version":"v2","key":%q}]`,
				previousSecret,
			)
		}},
		{name: "duplicate previous version", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON"] = fmt.Sprintf(
				`[{"version":"v1","key":%q},{"version":"v1","key":%q}]`,
				previousSecret,
				strings.Repeat("O", 40),
			)
		}},
		{name: "short previous key", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON"] =
				`[{"version":"v1","key":"short-previous-lifecycle"}]`
		}},
		{name: "invalid previous version", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON"] = fmt.Sprintf(
				`[{"version":"bad/version","key":%q}]`,
				previousSecret,
			)
		}},
		{name: "unknown JSON field", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON"] = fmt.Sprintf(
				`[{"version":"v1","key":%q,"secret_ref":"unknown-field-private-value"}]`,
				previousSecret,
			)
		}},
		{name: "trailing JSON", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON"] = fmt.Sprintf(
				`[{"version":"v1","key":%q}] {"private":"trailing-private-value"}`,
				previousSecret,
			)
		}},
		{name: "non array JSON", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_PREVIOUS_KEYS_JSON"] =
				`{"version":"v1","key":"non-array-private-value"}`
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			values := cloneStrings(base)
			test.mutate(values)
			_, err := identityLifecycleKeyRuntimeConfigFromEnv(lookup(values))
			if err == nil {
				t.Fatal("unsafe lifecycle keyring configuration was accepted")
			}
			for _, secret := range []string{
				activeSecret,
				previousSecret,
				"short-active-lifecycle-secret",
				"short-previous-lifecycle",
				"unknown-field-private-value",
				"trailing-private-value",
				"non-array-private-value",
			} {
				if strings.Contains(err.Error(), secret) {
					t.Fatalf("lifecycle keyring error leaked secret material: %v", err)
				}
			}
		})
	}
}

func TestProductionIdentityLifecycleKeyringFailsBeforeDatabaseAccess(t *testing.T) {
	const dsnSecret = "postgres://lifecycle-db-secret@database-must-not-be-contacted.invalid/ashr"
	base := map[string]string{
		"ASHR_POSTGRES_DSN":                         dsnSecret,
		"ASHR_IDENTITY_SESSION_HMAC_ACTIVE_VERSION": "v1",
		"ASHR_IDENTITY_SESSION_HMAC_KEY":            strings.Repeat("S", 40),
		"ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION": "v1",
	}
	for _, missing := range []string{
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION",
		"ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY",
	} {
		values := cloneStrings(base)
		if missing != "ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION" {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_ACTIVE_VERSION"] = "v1"
		}
		if missing != "ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY" {
			values["ASHR_IDENTITY_LIFECYCLE_RECEIPT_KEY"] = strings.Repeat("L", 40)
		}
		_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(values))
		if err == nil || !strings.Contains(err.Error(), missing) {
			t.Fatalf("missing %s did not fail before database access: %v", missing, err)
		}
		if strings.Contains(err.Error(), dsnSecret) {
			t.Fatalf("lifecycle keyring error leaked the database configuration: %v", err)
		}
	}
}

func TestIdentitySessionHMACRuntimeConfigRejectsUnsafeInputsWithoutEchoingKeys(t *testing.T) {
	activeSecret := "active-secret-value-that-must-not-leak-123456"
	previousSecret := "previous-secret-value-that-must-not-leak-1234"
	base := map[string]string{
		"ASHR_IDENTITY_SESSION_HMAC_ACTIVE_VERSION": "v2",
		"ASHR_IDENTITY_SESSION_HMAC_KEY":            activeSecret,
		"ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION": "v1",
		"ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON": fmt.Sprintf(
			`[{"version":"v1","key":%q,"retire_at":"2027-09-01T00:00:00Z"}]`,
			previousSecret,
		),
	}
	tests := []struct {
		name   string
		mutate func(map[string]string)
	}{
		{name: "short active key", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_SESSION_HMAC_KEY"] = "short-active-secret"
		}},
		{name: "duplicate active version", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON"] = fmt.Sprintf(
				`[{"version":"v2","key":%q,"retire_at":"2027-09-01T00:00:00Z"}]`,
				previousSecret,
			)
		}},
		{name: "short previous key", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON"] =
				`[{"version":"v1","key":"short-previous-secret","retire_at":"2027-09-01T00:00:00Z"}]`
		}},
		{name: "unknown JSON field", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON"] = fmt.Sprintf(
				`[{"version":"v1","key":%q,"retire_at":"2027-09-01T00:00:00Z","raw_secret":%q}]`,
				previousSecret,
				"unknown-field-secret-value",
			)
		}},
		{name: "legacy version missing", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION"] = "v0"
		}},
		{name: "retirement metadata missing", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON"] = fmt.Sprintf(
				`[{"version":"v1","key":%q}]`,
				previousSecret,
			)
		}},
		{name: "retirement metadata invalid", mutate: func(values map[string]string) {
			values["ASHR_IDENTITY_SESSION_HMAC_PREVIOUS_KEYS_JSON"] = fmt.Sprintf(
				`[{"version":"v1","key":%q,"retire_at":"not-a-timestamp"}]`,
				previousSecret,
			)
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			values := cloneStrings(base)
			test.mutate(values)
			_, err := identitySessionHMACRuntimeConfigFromEnv(lookup(values))
			if err == nil {
				t.Fatal("unsafe keyring configuration was accepted")
			}
			for _, secret := range []string{
				activeSecret,
				previousSecret,
				"short-active-secret",
				"short-previous-secret",
				"unknown-field-secret-value",
			} {
				if strings.Contains(err.Error(), secret) {
					t.Fatalf("keyring error leaked secret material: %v", err)
				}
			}
		})
	}
}

func TestProductionIdentityRuntimeRequiresExplicitVersionedKeyringBeforeDatabaseAccess(t *testing.T) {
	_, err := newIdentityRuntimeFromEnv(context.Background(), lookup(map[string]string{
		"ASHR_POSTGRES_DSN":                         "postgres://runtime-must-not-connect.invalid/ashr",
		"ASHR_IDENTITY_SESSION_HMAC_KEY":            strings.Repeat("A", 40),
		"ASHR_IDENTITY_SESSION_HMAC_ACTIVE_VERSION": "v2",
	}))
	if err == nil || !strings.Contains(err.Error(), "ASHR_IDENTITY_SESSION_HMAC_LEGACY_VERSION") {
		t.Fatalf("production runtime accepted an implicit legacy version: %v", err)
	}
}

func TestProductionIdentitySessionCookieTransportUsesExplicitProxyTrustOnly(t *testing.T) {
	transport, err := productionIdentitySessionReceiptTransportFromEnv(lookup(map[string]string{
		"ASHR_IDENTITY_SESSION_COOKIE_MAX_AGE_SECONDS":     "3600",
		"ASHR_IDENTITY_REFRESH_COOKIE_MAX_AGE_SECONDS":     "7200",
		"ASHR_IDENTITY_SESSION_COOKIE_TRUSTED_PROXY_CIDRS": "10.0.0.0/8,2001:db8:1234::/48",
		"ASHR_IDENTITY_VERIFICATION_SMTP_ENABLED":          "true",
		"ASHR_SMTP_AUTH_CODE":                              "ignored-production-smtp-secret",
	}))
	if err != nil {
		t.Fatal(err)
	}
	directTLS := httptest.NewRequest(http.MethodPost, "https://api.example.test/verify", nil)
	if err := transport.ValidateIdentitySessionRequest(directTLS); err != nil {
		t.Fatalf("direct TLS rejected: %v", err)
	}
	untrusted := httptest.NewRequest(http.MethodPost, "http://api.example.test/verify", nil)
	untrusted.RemoteAddr = "203.0.113.7:3000"
	untrusted.Header.Set("X-Forwarded-Proto", "https")
	if err := transport.ValidateIdentitySessionRequest(untrusted); err == nil {
		t.Fatal("untrusted forwarded scheme was accepted")
	}
	trusted := httptest.NewRequest(http.MethodPost, "http://api.example.test/verify", nil)
	trusted.RemoteAddr = "10.2.3.4:3000"
	trusted.Header.Set("X-Forwarded-Proto", "https")
	if err := transport.ValidateIdentitySessionRequest(trusted); err != nil {
		t.Fatalf("trusted proxy HTTPS rejected: %v", err)
	}
}

func TestProductionIdentitySessionCookieTransportRejectsInvalidEnvWithoutEcho(t *testing.T) {
	for _, values := range []map[string]string{
		{
			"ASHR_IDENTITY_SESSION_COOKIE_MAX_AGE_SECONDS": "invalid-max-age-secret",
		},
		{
			"ASHR_IDENTITY_REFRESH_COOKIE_MAX_AGE_SECONDS": "invalid-refresh-max-age-secret",
		},
		{
			"ASHR_IDENTITY_SESSION_COOKIE_TRUSTED_PROXY_CIDRS": "invalid-cidr-secret",
		},
		{
			"ASHR_IDENTITY_SESSION_COOKIE_TRUSTED_PROXY_CIDRS": "10.0.0.1/8,10.0.0.0/8",
		},
	} {
		_, err := productionIdentitySessionReceiptTransportFromEnv(lookup(values))
		if err == nil {
			t.Fatalf("invalid cookie transport config was accepted: %#v", values)
		}
		for _, value := range values {
			if strings.Contains(err.Error(), value) {
				t.Fatalf("cookie transport error leaked configuration value: %v", err)
			}
		}
	}
}

func cloneStrings(values map[string]string) map[string]string {
	cloned := make(map[string]string, len(values))
	for key, value := range values {
		cloned[key] = value
	}
	return cloned
}

func assertErrorOmitsValues(t *testing.T, err error, values map[string]string) {
	t.Helper()
	for _, value := range values {
		if value != "" && strings.Contains(err.Error(), value) {
			t.Fatalf("configuration error leaked a value: %v", err)
		}
	}
}

func productionIdentityDeliveryVaultTestEnv(t *testing.T) map[string]string {
	t.Helper()
	privateKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	template := &x509.Certificate{
		SerialNumber:          big.NewInt(now.UnixNano()),
		Subject:               pkix.Name{CommonName: "runtime-vault-client"},
		NotBefore:             now.Add(-time.Minute),
		NotAfter:              now.Add(time.Hour),
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
		BasicConstraintsValid: true,
		IsCA:                  true,
	}
	encodedCertificate, err := x509.CreateCertificate(
		rand.Reader,
		template,
		template,
		&privateKey.PublicKey,
		privateKey,
	)
	if err != nil {
		t.Fatal(err)
	}
	encodedPrivateKey, err := x509.MarshalPKCS8PrivateKey(privateKey)
	if err != nil {
		t.Fatal(err)
	}
	certificatePEM := pem.EncodeToMemory(&pem.Block{
		Type:  "CERTIFICATE",
		Bytes: encodedCertificate,
	})
	privateKeyPEM := pem.EncodeToMemory(&pem.Block{
		Type:  "PRIVATE KEY",
		Bytes: encodedPrivateKey,
	})
	tempDirectory := t.TempDir()
	caPath := filepath.Join(tempDirectory, "vault-ca-private-path.pem")
	certificatePath := filepath.Join(tempDirectory, "vault-client-certificate-private-path.pem")
	privateKeyPath := filepath.Join(tempDirectory, "vault-client-key-private-path.pem")
	for path, content := range map[string][]byte{
		caPath:          certificatePEM,
		certificatePath: certificatePEM,
		privateKeyPath:  privateKeyPEM,
	} {
		if err := os.WriteFile(path, content, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	return map[string]string{
		"ASHR_IDENTITY_DELIVERY_VAULT_SEAL_URL":              "https://vault-runtime-secret.invalid/v1/seal",
		"ASHR_IDENTITY_DELIVERY_VAULT_DELETE_URL":            "https://vault-runtime-secret.invalid/v1/delete",
		"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CA_FILE":          caPath,
		"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_CERT_FILE": certificatePath,
		"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_CLIENT_KEY_FILE":  privateKeyPath,
		"ASHR_IDENTITY_DELIVERY_VAULT_MTLS_SERVER_NAME":      "vault-runtime-secret.invalid",
	}
}
