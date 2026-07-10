package main

import (
	"context"
	"strings"
	"testing"

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
	if err == nil || !strings.Contains(err.Error(), "durable store and sender") {
		t.Fatalf("production verification did not fail closed: %v", err)
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
			t.Fatalf("SMTP configuration error leaked a value: %v", err)
		}
	}
}
