package ashrclone

import (
	"errors"
	"net/url"
	"path"
	"strings"
)

const (
	IdentityVerificationChallengeQueryParameter = "challenge_id"
	IdentityVerificationPurposeQueryParameter   = "purpose"
)

// BuildIdentityVerificationBrowserURL appends only the opaque challenge
// handle and its non-secret purpose to an operator-configured HTTPS webapp
// route. The raw identifier and verification code must never enter this URL.
func BuildIdentityVerificationBrowserURL(
	rawBaseURL string,
	challengeID string,
	purpose IdentityVerificationPurpose,
) (string, error) {
	baseURL, err := strictIdentityVerificationBrowserBaseURL(rawBaseURL)
	if err != nil {
		return "", err
	}
	challengeID = strings.TrimSpace(challengeID)
	if !validPostgresIdentityVerificationHandle(challengeID, "ivc_", 256) ||
		!validIdentityDeliveryPurpose(purpose) {
		return "", errors.New("identity verification browser context is invalid")
	}
	query := url.Values{}
	query.Set(IdentityVerificationChallengeQueryParameter, challengeID)
	query.Set(IdentityVerificationPurposeQueryParameter, string(purpose))
	baseURL.RawQuery = query.Encode()
	return baseURL.String(), nil
}

func strictIdentityVerificationBrowserBaseURL(raw string) (*url.URL, error) {
	if raw == "" || raw != strings.TrimSpace(raw) ||
		strings.ContainsAny(raw, "\x00\r\n\\#") {
		return nil, errors.New("identity verification browser URL is invalid")
	}
	parsed, err := url.ParseRequestURI(raw)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" ||
		parsed.Hostname() == "" || parsed.User != nil || parsed.Opaque != "" ||
		parsed.Fragment != "" || parsed.RawQuery != "" || parsed.ForceQuery {
		return nil, errors.New("identity verification browser URL must be an absolute HTTPS URL without query or fragment")
	}
	if parsed.Path == "" || !strings.HasPrefix(parsed.Path, "/") ||
		path.Clean(parsed.Path) != parsed.Path ||
		strings.Contains(parsed.EscapedPath(), "%2f") ||
		strings.Contains(parsed.EscapedPath(), "%2F") ||
		strings.Contains(parsed.EscapedPath(), "%5c") ||
		strings.Contains(parsed.EscapedPath(), "%5C") {
		return nil, errors.New("identity verification browser URL path is invalid")
	}
	return parsed, nil
}
