package releasefoundry

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const verifierOutputLimit = 64 * 1024

var verifierEnvName = regexp.MustCompile(`^[A-Z][A-Z0-9_]{0,127}$`)

type RustIngestionVerifierConfig struct {
	Executable     string
	KeyEnv         string
	Timeout        time.Duration
	MaxObjectBytes uint64
	MaxTotalBytes  uint64
	commandContext func(context.Context, string, ...string) *exec.Cmd
}

type RustIngestionVerificationRequest struct {
	TenantID   string
	ProjectID  string
	RunID      string
	Bundle     string
	ObjectRoot string
}

type RustIngestionVerification struct {
	SchemaVersion             string
	Algorithm                 string
	KeyID                     string
	AuthenticatedBundleDigest string
	EvidenceDigest            string
	EvidenceItems             uint64
	ObjectsVerified           uint64
	TotalSizeBytes            uint64
	ExpiresAtUnixMS           uint64
}

type verifierResponse struct {
	Status                      string `json:"status"`
	VerificationLevel           string `json:"verification_level"`
	ManifestAuthenticated       bool   `json:"manifest_authenticated"`
	ObjectVerificationPerformed bool   `json:"object_verification_performed"`
	SchemaVersion               string `json:"schema_version"`
	Algorithm                   string `json:"algorithm"`
	KeyID                       string `json:"key_id"`
	AuthenticatedBundleDigest   string `json:"authenticated_bundle_digest"`
	EvidenceDigest              string `json:"evidence_digest"`
	EvidenceItems               uint64 `json:"evidence_items"`
	ObjectsVerified             uint64 `json:"objects_verified"`
	TotalSizeBytes              uint64 `json:"total_size_bytes"`
	ExpiresAtUnixMS             uint64 `json:"expires_at_unix_ms"`
}

type RustVerifierError struct {
	Code string
}

func (e *RustVerifierError) Error() string { return "rust ingestion verifier: " + e.Code }

func (c RustIngestionVerifierConfig) Verify(ctx context.Context, request RustIngestionVerificationRequest) (RustIngestionVerification, error) {
	if err := c.validate(request); err != nil {
		return RustIngestionVerification{}, err
	}
	timeoutCtx, cancel := context.WithTimeout(ctx, c.Timeout)
	defer cancel()

	args := []string{
		"verify-signed-bundle-objects", request.Bundle,
		"--key-env", c.KeyEnv,
		"--object-root", request.ObjectRoot,
		"--max-object-bytes", strconv.FormatUint(c.MaxObjectBytes, 10),
		"--max-total-bytes", strconv.FormatUint(c.MaxTotalBytes, 10),
		"--expected-tenant-digest", scopeDigest(request.TenantID),
		"--expected-project-digest", scopeDigest(request.ProjectID),
		"--expected-bundle-id-digest", scopeDigest(request.RunID),
	}
	commandContext := c.commandContext
	if commandContext == nil {
		commandContext = exec.CommandContext
	}
	command := commandContext(timeoutCtx, c.Executable, args...)
	var stdout limitedBuffer
	var stderr limitedBuffer
	command.Stdout = &stdout
	command.Stderr = &stderr
	runErr := command.Run()
	if errors.Is(timeoutCtx.Err(), context.DeadlineExceeded) {
		return RustIngestionVerification{}, &RustVerifierError{Code: "timeout"}
	}
	if errors.Is(timeoutCtx.Err(), context.Canceled) {
		return RustIngestionVerification{}, &RustVerifierError{Code: "cancelled"}
	}
	if runErr != nil {
		return RustIngestionVerification{}, &RustVerifierError{Code: "process_failed"}
	}
	if stdout.overflow {
		return RustIngestionVerification{}, &RustVerifierError{Code: "output_too_large"}
	}
	response, err := decodeVerifierResponse(stdout.Bytes())
	if err != nil {
		return RustIngestionVerification{}, err
	}
	return RustIngestionVerification{
		SchemaVersion: response.SchemaVersion, Algorithm: response.Algorithm, KeyID: response.KeyID,
		AuthenticatedBundleDigest: response.AuthenticatedBundleDigest,
		EvidenceDigest:            response.EvidenceDigest, EvidenceItems: response.EvidenceItems,
		ObjectsVerified: response.ObjectsVerified, TotalSizeBytes: response.TotalSizeBytes,
		ExpiresAtUnixMS: response.ExpiresAtUnixMS,
	}, nil
}

func (c RustIngestionVerifierConfig) validate(request RustIngestionVerificationRequest) error {
	if strings.TrimSpace(c.Executable) == "" || !filepath.IsAbs(c.Executable) {
		return &RustVerifierError{Code: "invalid_executable"}
	}
	if !verifierEnvName.MatchString(c.KeyEnv) {
		return &RustVerifierError{Code: "invalid_key_env"}
	}
	if c.Timeout <= 0 || c.MaxObjectBytes == 0 || c.MaxTotalBytes < c.MaxObjectBytes {
		return &RustVerifierError{Code: "invalid_limits"}
	}
	if strings.TrimSpace(request.TenantID) == "" || strings.TrimSpace(request.ProjectID) == "" || strings.TrimSpace(request.RunID) == "" {
		return &RustVerifierError{Code: "invalid_scope"}
	}
	if !filepath.IsAbs(request.Bundle) || !filepath.IsAbs(request.ObjectRoot) {
		return &RustVerifierError{Code: "invalid_path"}
	}
	return nil
}

func decodeVerifierResponse(raw []byte) (verifierResponse, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	var response verifierResponse
	if err := decoder.Decode(&response); err != nil {
		return verifierResponse{}, &RustVerifierError{Code: "malformed_output"}
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return verifierResponse{}, &RustVerifierError{Code: "trailing_output"}
	}
	if response.Status != "ok" || response.VerificationLevel != "objects_verified" ||
		!response.ManifestAuthenticated || !response.ObjectVerificationPerformed ||
		response.EvidenceItems == 0 || response.ObjectsVerified != response.EvidenceItems ||
		response.SchemaVersion == "" || response.Algorithm == "" || response.KeyID == "" ||
		!isLowerSHA256(response.AuthenticatedBundleDigest) || !isLowerSHA256(response.EvidenceDigest) {
		return verifierResponse{}, &RustVerifierError{Code: "invalid_result"}
	}
	return response, nil
}

func scopeDigest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func isLowerSHA256(value string) bool {
	if len(value) != 64 {
		return false
	}
	for _, char := range value {
		if !(char >= '0' && char <= '9') && !(char >= 'a' && char <= 'f') {
			return false
		}
	}
	return true
}

type limitedBuffer struct {
	data     bytes.Buffer
	overflow bool
}

func (b *limitedBuffer) Write(input []byte) (int, error) {
	original := len(input)
	remaining := verifierOutputLimit - b.data.Len()
	if remaining <= 0 {
		b.overflow = true
		return original, nil
	}
	if len(input) > remaining {
		b.overflow = true
		input = input[:remaining]
	}
	_, _ = b.data.Write(input)
	return original, nil
}

func (b *limitedBuffer) Bytes() []byte { return b.data.Bytes() }
