package releasefoundry

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestRustIngestionVerifierBindsTrustedScope(t *testing.T) {
	var captured []string
	config := validRustVerifierConfig(t)
	config.commandContext = func(ctx context.Context, executable string, args ...string) *exec.Cmd {
		captured = append([]string(nil), args...)
		return helperVerifierCommand(ctx, "success")
	}
	result, err := config.Verify(context.Background(), validVerificationRequest(t))
	if err != nil {
		t.Fatal(err)
	}
	if result.ObjectsVerified != 1 {
		t.Fatalf("unexpected result: %#v", result)
	}
	assertFlagValue(t, captured, "--expected-tenant-digest", scopeDigest("tenant-1"))
	assertFlagValue(t, captured, "--expected-project-digest", scopeDigest("project-1"))
	assertFlagValue(t, captured, "--expected-bundle-id-digest", scopeDigest("run-1"))
}

func TestRustIngestionVerifierFailsClosed(t *testing.T) {
	cases := []struct {
		name string
		mode string
		code string
	}{
		{"nonzero", "nonzero", "process_failed"},
		{"malformed", "malformed", "malformed_output"},
		{"trailing", "trailing", "trailing_output"},
		{"false success", "false-success", "invalid_result"},
		{"digest", "bad-digest", "invalid_result"},
		{"unknown field", "unknown", "malformed_output"},
		{"oversized", "oversized", "output_too_large"},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			config := validRustVerifierConfig(t)
			config.commandContext = func(ctx context.Context, executable string, args ...string) *exec.Cmd {
				return helperVerifierCommand(ctx, test.mode)
			}
			_, err := config.Verify(context.Background(), validVerificationRequest(t))
			assertVerifierCode(t, err, test.code)
		})
	}
}

func TestRustIngestionVerifierTimeoutAndCancellation(t *testing.T) {
	t.Run("timeout", func(t *testing.T) {
		config := validRustVerifierConfig(t)
		config.Timeout = 25 * time.Millisecond
		config.commandContext = func(ctx context.Context, executable string, args ...string) *exec.Cmd {
			return helperVerifierCommand(ctx, "sleep")
		}
		_, err := config.Verify(context.Background(), validVerificationRequest(t))
		assertVerifierCode(t, err, "timeout")
	})
	t.Run("cancelled", func(t *testing.T) {
		config := validRustVerifierConfig(t)
		config.commandContext = func(ctx context.Context, executable string, args ...string) *exec.Cmd {
			return helperVerifierCommand(ctx, "sleep")
		}
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		_, err := config.Verify(ctx, validVerificationRequest(t))
		assertVerifierCode(t, err, "cancelled")
	})
}

func TestRustIngestionVerifierRejectsInvalidConfigurationAndPaths(t *testing.T) {
	request := validVerificationRequest(t)
	cases := []struct {
		name   string
		mutate func(*RustIngestionVerifierConfig, *RustIngestionVerificationRequest)
		code   string
	}{
		{"executable", func(c *RustIngestionVerifierConfig, r *RustIngestionVerificationRequest) { c.Executable = "relative" }, "invalid_executable"},
		{"key env", func(c *RustIngestionVerifierConfig, r *RustIngestionVerificationRequest) { c.KeyEnv = "bad-env" }, "invalid_key_env"},
		{"limits", func(c *RustIngestionVerifierConfig, r *RustIngestionVerificationRequest) { c.MaxTotalBytes = 1 }, "invalid_limits"},
		{"scope", func(c *RustIngestionVerifierConfig, r *RustIngestionVerificationRequest) { r.RunID = "" }, "invalid_scope"},
		{"bundle path", func(c *RustIngestionVerifierConfig, r *RustIngestionVerificationRequest) { r.Bundle = "../escape.json" }, "invalid_path"},
		{"object root", func(c *RustIngestionVerifierConfig, r *RustIngestionVerificationRequest) { r.ObjectRoot = "relative" }, "invalid_path"},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			config := validRustVerifierConfig(t)
			candidate := request
			test.mutate(&config, &candidate)
			_, err := config.Verify(context.Background(), candidate)
			assertVerifierCode(t, err, test.code)
		})
	}
}

func TestRustVerifierHelperProcess(t *testing.T) {
	if os.Getenv("RELEASEFOUNDRY_GO_VERIFIER_HELPER") != "1" {
		return
	}
	mode := os.Getenv("RELEASEFOUNDRY_GO_VERIFIER_MODE")
	valid := `{"status":"ok","verification_level":"objects_verified","manifest_authenticated":true,"object_verification_performed":true,"schema_version":"releasefoundry.a1.authenticated_evidence_bundle.v2","algorithm":"hmac-sha256","key_id":"round54:key","authenticated_bundle_digest":"` + strings.Repeat("a", 64) + `","evidence_digest":"` + strings.Repeat("b", 64) + `","evidence_items":1,"objects_verified":1,"total_size_bytes":7,"expires_at_unix_ms":1750000060000}`
	switch mode {
	case "success":
		_, _ = os.Stdout.WriteString(valid)
	case "nonzero":
		os.Exit(9)
	case "malformed":
		_, _ = os.Stdout.WriteString("{")
	case "trailing":
		_, _ = os.Stdout.WriteString(valid + `{}`)
	case "false-success":
		_, _ = os.Stdout.WriteString(strings.Replace(valid, `"manifest_authenticated":true`, `"manifest_authenticated":false`, 1))
	case "bad-digest":
		_, _ = os.Stdout.WriteString(strings.Replace(valid, strings.Repeat("a", 64), "ABC", 1))
	case "unknown":
		_, _ = os.Stdout.WriteString(strings.TrimSuffix(valid, "}") + `,"secret":"nope"}`)
	case "oversized":
		_, _ = os.Stdout.WriteString(strings.Repeat("x", verifierOutputLimit+1))
	case "sleep":
		time.Sleep(5 * time.Second)
	}
	os.Exit(0)
}

func validRustVerifierConfig(t *testing.T) RustIngestionVerifierConfig {
	t.Helper()
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	return RustIngestionVerifierConfig{
		Executable: executable, KeyEnv: "RELEASEFOUNDRY_TEST_VERIFIER_KEY",
		Timeout: 5 * time.Second, MaxObjectBytes: 1024, MaxTotalBytes: 4096,
	}
}

func validVerificationRequest(t *testing.T) RustIngestionVerificationRequest {
	t.Helper()
	root := t.TempDir()
	return RustIngestionVerificationRequest{
		TenantID: "tenant-1", ProjectID: "project-1", RunID: "run-1",
		Bundle: filepath.Join(root, "bundle.json"), ObjectRoot: root,
	}
}

func helperVerifierCommand(ctx context.Context, mode string) *exec.Cmd {
	command := exec.CommandContext(ctx, os.Args[0], "-test.run=TestRustVerifierHelperProcess")
	command.Env = append(os.Environ(), "RELEASEFOUNDRY_GO_VERIFIER_HELPER=1", "RELEASEFOUNDRY_GO_VERIFIER_MODE="+mode)
	return command
}

func assertFlagValue(t *testing.T, args []string, flag, expected string) {
	t.Helper()
	for index := 0; index+1 < len(args); index++ {
		if args[index] == flag {
			if args[index+1] != expected {
				t.Fatalf("%s = %q, want %q", flag, args[index+1], expected)
			}
			return
		}
	}
	t.Fatalf("missing %s in %v", flag, args)
}

func assertVerifierCode(t *testing.T, err error, expected string) {
	t.Helper()
	var verifierErr *RustVerifierError
	if !errors.As(err, &verifierErr) || verifierErr.Code != expected {
		t.Fatalf("error = %#v, want verifier code %q", err, expected)
	}
}
