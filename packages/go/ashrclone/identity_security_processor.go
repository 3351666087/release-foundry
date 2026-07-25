package ashrclone

import (
	"context"
	"errors"
	"net/url"
	"regexp"
	"strings"
	"unicode/utf8"
)

var ErrIdentitySecurityProcessorUnavailable = errors.New("identity security processor unavailable")
var ErrIdentitySecurityProcessorRejected = errors.New("identity security processor rejected")

var identitySecurityProcessorReferencePattern = regexp.MustCompile(
	`^isr_[A-Za-z0-9_-]{24,508}$`,
)
var identitySecurityProcessorChallengePattern = regexp.MustCompile(
	`^isc_[A-Za-z0-9_-]{24,252}$`,
)
var identitySecurityProcessorHandoffPattern = regexp.MustCompile(
	`^ish_[A-Za-z0-9_-]{24,252}$`,
)
var identitySecurityProcessorCleanupPattern = regexp.MustCompile(
	`^isx_[A-Za-z0-9_-]{24,252}$`,
)
var identitySecurityProcessorKeyVersionPattern = regexp.MustCompile(
	`^[A-Za-z0-9][A-Za-z0-9._:-]{1,63}$`,
)
var identitySecurityRecoveryCodePattern = regexp.MustCompile(
	`^[A-Z0-9][A-Z0-9-]{7,63}$`,
)

type IdentitySecuritySecretProcessRequest struct {
	AccountID      string
	Operation      string
	IdempotencyKey string
	Password       string
}

type IdentitySecuritySecretProcessResult struct {
	SecretRef               string
	SecretDigest            string
	KeyVersion              string
	ConfirmationChallengeID string
	HandoffID               string
	CleanupToken            string
}

type IdentitySecuritySecretConfirmRequest struct {
	AccountID      string
	ChallengeID    string
	Code           string
	IdempotencyKey string
}

type IdentitySecuritySecretConfirmResult struct {
	RecoveryBatchDigest string
	RecoveryCodeCount   int
	KeyVersion          string
	HandoffID           string
	CleanupToken        string
}

type IdentitySecuritySecretHandoffRequest struct {
	AccountID      string
	Operation      string
	IdempotencyKey string
	HandoffID      string
}

type IdentitySecuritySecretHandoff struct {
	ProvisioningURI string
	RecoveryCodes   []string
}

type IdentitySecuritySecretCleanupRequest struct {
	AccountID      string
	Operation      string
	IdempotencyKey string
	CleanupToken   string
}

// IdentitySecuritySecretProcessor is the only boundary allowed to receive raw
// password or TOTP proof material. All database-facing components receive only
// opaque references and keyed digests.
type IdentitySecuritySecretProcessor interface {
	ProcessIdentitySecuritySecret(
		context.Context,
		IdentitySecuritySecretProcessRequest,
	) (IdentitySecuritySecretProcessResult, error)
	ConfirmIdentitySecuritySecret(
		context.Context,
		IdentitySecuritySecretConfirmRequest,
	) (IdentitySecuritySecretConfirmResult, error)
	ConsumeIdentitySecuritySecretHandoff(
		context.Context,
		IdentitySecuritySecretHandoffRequest,
	) (IdentitySecuritySecretHandoff, error)
	CleanupIdentitySecuritySecret(
		context.Context,
		IdentitySecuritySecretCleanupRequest,
	) error
}

func validIdentitySecurityPassword(password string) bool {
	if !utf8.ValidString(password) {
		return false
	}
	length := utf8.RuneCountInString(password)
	return length >= 12 && length <= 256 &&
		!strings.ContainsAny(password, "\x00\r\n")
}

func validIdentitySecurityTOTPCode(code string) bool {
	if len(code) != 6 {
		return false
	}
	for _, character := range code {
		if character < '0' || character > '9' {
			return false
		}
	}
	return true
}

func validIdentitySecuritySecretProcessRequest(
	request IdentitySecuritySecretProcessRequest,
) bool {
	if !validPostgresIdentityVerificationUUID(strings.TrimSpace(request.AccountID)) ||
		!validIdentitySecurityIdempotencyKey(strings.TrimSpace(request.IdempotencyKey)) {
		return false
	}
	switch strings.TrimSpace(request.Operation) {
	case "password_enroll", "password_change", "password_recovery":
		return validIdentitySecurityPassword(request.Password)
	case "mfa_enroll":
		return request.Password == ""
	default:
		return false
	}
}

func validIdentitySecuritySecretProcessResult(
	operation string,
	result IdentitySecuritySecretProcessResult,
) bool {
	if !identitySecurityProcessorReferencePattern.MatchString(result.SecretRef) ||
		!validIdentitySecurityDigest(result.SecretDigest) ||
		!identitySecurityProcessorKeyVersionPattern.MatchString(result.KeyVersion) ||
		!identitySecurityProcessorCleanupPattern.MatchString(result.CleanupToken) {
		return false
	}
	switch strings.TrimSpace(operation) {
	case "password_enroll", "password_change", "password_recovery":
		return result.ConfirmationChallengeID == "" && result.HandoffID == ""
	case "mfa_enroll":
		return identitySecurityProcessorChallengePattern.MatchString(
			result.ConfirmationChallengeID,
		) && identitySecurityProcessorHandoffPattern.MatchString(result.HandoffID)
	default:
		return false
	}
}

func validIdentitySecuritySecretConfirmRequest(
	request IdentitySecuritySecretConfirmRequest,
) bool {
	return validPostgresIdentityVerificationUUID(strings.TrimSpace(request.AccountID)) &&
		identitySecurityProcessorChallengePattern.MatchString(
			strings.TrimSpace(request.ChallengeID),
		) &&
		validIdentitySecurityTOTPCode(strings.TrimSpace(request.Code)) &&
		validIdentitySecurityIdempotencyKey(strings.TrimSpace(request.IdempotencyKey))
}

func validIdentitySecuritySecretConfirmResult(
	result IdentitySecuritySecretConfirmResult,
) bool {
	return validIdentitySecurityDigest(result.RecoveryBatchDigest) &&
		result.RecoveryCodeCount >= 6 && result.RecoveryCodeCount <= 20 &&
		identitySecurityProcessorKeyVersionPattern.MatchString(result.KeyVersion) &&
		identitySecurityProcessorHandoffPattern.MatchString(result.HandoffID) &&
		identitySecurityProcessorCleanupPattern.MatchString(result.CleanupToken)
}

func validIdentitySecuritySecretHandoffRequest(
	request IdentitySecuritySecretHandoffRequest,
) bool {
	if !validPostgresIdentityVerificationUUID(strings.TrimSpace(request.AccountID)) ||
		!validIdentitySecurityIdempotencyKey(strings.TrimSpace(request.IdempotencyKey)) ||
		!identitySecurityProcessorHandoffPattern.MatchString(
			strings.TrimSpace(request.HandoffID),
		) {
		return false
	}
	return request.Operation == "mfa_enroll" || request.Operation == "mfa_confirm"
}

func validIdentitySecuritySecretHandoff(
	operation string,
	handoff IdentitySecuritySecretHandoff,
) bool {
	switch operation {
	case "mfa_enroll":
		return validIdentitySecurityProvisioningURI(handoff.ProvisioningURI) &&
			len(handoff.RecoveryCodes) == 0
	case "mfa_confirm":
		return handoff.ProvisioningURI == "" &&
			validIdentitySecurityRecoveryCodes(handoff.RecoveryCodes)
	default:
		return false
	}
}

func validIdentitySecurityProvisioningURI(value string) bool {
	if value == "" || value != strings.TrimSpace(value) ||
		len(value) > 2048 || strings.ContainsAny(value, "\x00\r\n\t") {
		return false
	}
	parsed, err := url.ParseRequestURI(value)
	if err != nil || parsed.Scheme != "otpauth" ||
		parsed.Host != "totp" || parsed.User != nil ||
		parsed.RawQuery == "" || parsed.Fragment != "" ||
		strings.TrimSpace(parsed.Query().Get("secret")) == "" {
		return false
	}
	return true
}

func validIdentitySecurityRecoveryCodes(codes []string) bool {
	if len(codes) < 6 || len(codes) > 20 {
		return false
	}
	seen := make(map[string]struct{}, len(codes))
	for _, code := range codes {
		if !identitySecurityRecoveryCodePattern.MatchString(code) {
			return false
		}
		if _, exists := seen[code]; exists {
			return false
		}
		seen[code] = struct{}{}
	}
	return true
}

func validIdentitySecuritySecretCleanupRequest(
	request IdentitySecuritySecretCleanupRequest,
) bool {
	if !validPostgresIdentityVerificationUUID(strings.TrimSpace(request.AccountID)) ||
		!validIdentitySecurityIdempotencyKey(strings.TrimSpace(request.IdempotencyKey)) ||
		!identitySecurityProcessorCleanupPattern.MatchString(
			strings.TrimSpace(request.CleanupToken),
		) {
		return false
	}
	switch request.Operation {
	case "password_enroll", "password_change", "password_recovery",
		"mfa_enroll", "mfa_confirm":
		return true
	default:
		return false
	}
}
