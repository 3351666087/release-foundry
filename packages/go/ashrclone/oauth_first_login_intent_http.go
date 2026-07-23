package ashrclone

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const (
	OAuthFirstLoginIntentCookieName = "__Host-ashr_oauth_intent"

	maximumOAuthFirstLoginIntentCookieBytes = 4096
)

var (
	errOAuthFirstLoginIntentUnavailable = errors.New("OAuth first-login browser intent is unavailable")
	errOAuthFirstLoginIntentInvalid     = errors.New("OAuth first-login browser intent is invalid")
)

type OAuthFirstLoginIntentIssue struct {
	IntentID       string
	Provider       string
	Purpose        OAuthPurpose
	OrganizationID string
	ProjectID      string
	StateHash      string
	ExpiresAt      time.Time
}

type OAuthFirstLoginIntentValidation struct {
	IntentID       string
	Provider       string
	Purpose        OAuthPurpose
	OrganizationID string
	ProjectID      string
	StateHash      string
}

// OAuthFirstLoginIntentTransport is the browser correlation boundary for the
// public provider redirect. Issuance requires exact same-origin browser
// metadata; callback validation permits the provider's top-level cross-site
// navigation but still binds the cookie to the original effective HTTPS host.
type OAuthFirstLoginIntentTransport interface {
	ValidateOAuthFirstLoginRequest(*http.Request) error
	IssueOAuthFirstLoginIntent(
		http.ResponseWriter,
		*http.Request,
		OAuthFirstLoginIntentIssue,
	) error
	ValidateOAuthFirstLoginIntent(
		*http.Request,
		OAuthFirstLoginIntentValidation,
	) error
	ClearOAuthFirstLoginIntent(http.ResponseWriter)
}

type oauthFirstLoginIntentCodec struct {
	aead        cipher.AEAD
	maxLifetime time.Duration
	now         func() time.Time
}

type oauthFirstLoginIntentPayload struct {
	SchemaVersion  string       `json:"schema_version"`
	IntentID       string       `json:"intent_id"`
	Provider       string       `json:"provider"`
	Purpose        OAuthPurpose `json:"purpose"`
	OrganizationID string       `json:"organization_id"`
	ProjectID      string       `json:"project_id"`
	StateHash      string       `json:"state_hash"`
	Origin         string       `json:"origin"`
	ExpiresAt      string       `json:"expires_at"`
}

func newOAuthFirstLoginIntentCodec(
	key []byte,
	maxLifetime time.Duration,
	now func() time.Time,
) (*oauthFirstLoginIntentCodec, error) {
	if len(key) == 0 {
		return nil, nil
	}
	if len(key) < 32 {
		return nil, fmt.Errorf("OAuth first-login browser intent key must contain at least 32 bytes")
	}
	if maxLifetime == 0 {
		maxLifetime = defaultIdentityBrowserIntentMaxLifetime
	}
	if maxLifetime < time.Second || maxLifetime > maximumIdentityBrowserIntentMaxLifetime {
		return nil, fmt.Errorf("OAuth first-login browser intent max lifetime must be between one second and 30 minutes")
	}
	if now == nil {
		now = time.Now
	}
	// The email and OAuth intent codecs may receive the same operator-managed
	// root key, but never share an AEAD key or associated-data domain.
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte("ashr.identity.oauth_first_login_intent.aead.v1"))
	derivedKey := mac.Sum(nil)
	block, err := aes.NewCipher(derivedKey)
	for index := range derivedKey {
		derivedKey[index] = 0
	}
	if err != nil {
		return nil, fmt.Errorf("configure OAuth first-login browser intent cipher: %w", err)
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("configure OAuth first-login browser intent AEAD: %w", err)
	}
	return &oauthFirstLoginIntentCodec{
		aead:        aead,
		maxLifetime: maxLifetime,
		now:         now,
	}, nil
}

func (transport *IdentitySessionCookieTransport) ValidateOAuthFirstLoginRequest(
	request *http.Request,
) error {
	return transport.ValidateIdentitySessionRequest(request)
}

func (transport *IdentitySessionCookieTransport) IssueOAuthFirstLoginIntent(
	writer http.ResponseWriter,
	request *http.Request,
	issue OAuthFirstLoginIntentIssue,
) error {
	if transport == nil || transport.oauthFirstLoginIntent == nil || writer == nil {
		return errOAuthFirstLoginIntentUnavailable
	}
	if err := transport.ValidateIdentitySessionRequest(request); err != nil {
		return err
	}
	origin, err := identityBrowserVerificationOrigin(request)
	if err != nil {
		return errOAuthFirstLoginIntentInvalid
	}
	now := transport.oauthFirstLoginIntent.now().UTC()
	expiresAt := issue.ExpiresAt.UTC()
	if !validOAuthFirstLoginIntentIssue(issue) || !expiresAt.After(now) ||
		expiresAt.After(now.Add(transport.oauthFirstLoginIntent.maxLifetime)) {
		return errOAuthFirstLoginIntentInvalid
	}
	payload, err := json.Marshal(oauthFirstLoginIntentPayload{
		SchemaVersion:  OAuthFirstLoginSchemaVersion,
		IntentID:       issue.IntentID,
		Provider:       issue.Provider,
		Purpose:        issue.Purpose,
		OrganizationID: issue.OrganizationID,
		ProjectID:      issue.ProjectID,
		StateHash:      issue.StateHash,
		Origin:         origin,
		ExpiresAt:      expiresAt.Format(time.RFC3339Nano),
	})
	if err != nil {
		return errOAuthFirstLoginIntentUnavailable
	}
	nonce := make([]byte, transport.oauthFirstLoginIntent.aead.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return errOAuthFirstLoginIntentUnavailable
	}
	sealed := transport.oauthFirstLoginIntent.aead.Seal(
		nonce,
		nonce,
		payload,
		[]byte(OAuthFirstLoginIntentCookieName+"|v1"),
	)
	cookieValue := "v1." + base64.RawURLEncoding.EncodeToString(sealed)
	maxAge := int(expiresAt.Sub(now) / time.Second)
	if len(cookieValue) > maximumOAuthFirstLoginIntentCookieBytes || maxAge < 1 {
		return errOAuthFirstLoginIntentInvalid
	}
	cookie := &http.Cookie{
		Name:     OAuthFirstLoginIntentCookieName,
		Value:    cookieValue,
		Path:     "/",
		Expires:  expiresAt,
		MaxAge:   maxAge,
		Secure:   true,
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
	}
	if err := cookie.Valid(); err != nil {
		return errOAuthFirstLoginIntentInvalid
	}
	http.SetCookie(writer, cookie)
	return nil
}

func (transport *IdentitySessionCookieTransport) ValidateOAuthFirstLoginIntent(
	request *http.Request,
	expected OAuthFirstLoginIntentValidation,
) error {
	if transport == nil || transport.oauthFirstLoginIntent == nil {
		return errOAuthFirstLoginIntentUnavailable
	}
	if err := transport.ValidateIdentitySessionRequest(request); err != nil {
		return err
	}
	if !validOAuthFirstLoginIntentValidation(expected) {
		return errOAuthFirstLoginIntentInvalid
	}
	cookie, err := uniqueOAuthFirstLoginIntentCookie(request)
	if err != nil {
		return errOAuthFirstLoginIntentInvalid
	}
	parts := strings.Split(cookie.Value, ".")
	if len(parts) != 2 || parts[0] != "v1" ||
		len(cookie.Value) > maximumOAuthFirstLoginIntentCookieBytes {
		return errOAuthFirstLoginIntentInvalid
	}
	sealed, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil || len(sealed) <= transport.oauthFirstLoginIntent.aead.NonceSize() ||
		!constantTimeIdentityBrowserValue(base64.RawURLEncoding.EncodeToString(sealed), parts[1]) {
		return errOAuthFirstLoginIntentInvalid
	}
	nonceSize := transport.oauthFirstLoginIntent.aead.NonceSize()
	plaintext, err := transport.oauthFirstLoginIntent.aead.Open(
		nil,
		sealed[:nonceSize],
		sealed[nonceSize:],
		[]byte(OAuthFirstLoginIntentCookieName+"|v1"),
	)
	if err != nil {
		return errOAuthFirstLoginIntentInvalid
	}
	var payload oauthFirstLoginIntentPayload
	if err := json.Unmarshal(plaintext, &payload); err != nil {
		return errOAuthFirstLoginIntentInvalid
	}
	expiresAt, err := time.Parse(time.RFC3339Nano, payload.ExpiresAt)
	if err != nil || !expiresAt.After(transport.oauthFirstLoginIntent.now().UTC()) {
		return errOAuthFirstLoginIntentInvalid
	}
	callbackOrigin, err := oauthFirstLoginCallbackOrigin(request)
	if err != nil || payload.SchemaVersion != OAuthFirstLoginSchemaVersion ||
		!constantTimeIdentityBrowserValue(payload.IntentID, expected.IntentID) ||
		!constantTimeIdentityBrowserValue(payload.Provider, expected.Provider) ||
		!constantTimeIdentityBrowserValue(string(payload.Purpose), string(expected.Purpose)) ||
		!constantTimeIdentityBrowserValue(payload.OrganizationID, expected.OrganizationID) ||
		!constantTimeIdentityBrowserValue(payload.ProjectID, expected.ProjectID) ||
		!constantTimeIdentityBrowserValue(payload.StateHash, expected.StateHash) ||
		!constantTimeIdentityBrowserValue(payload.Origin, callbackOrigin) {
		return errOAuthFirstLoginIntentInvalid
	}
	return nil
}

func (transport *IdentitySessionCookieTransport) ClearOAuthFirstLoginIntent(
	writer http.ResponseWriter,
) {
	if writer == nil {
		return
	}
	http.SetCookie(writer, &http.Cookie{
		Name:     OAuthFirstLoginIntentCookieName,
		Path:     "/",
		Expires:  time.Unix(1, 0).UTC(),
		MaxAge:   -1,
		Secure:   true,
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
	})
}

func uniqueOAuthFirstLoginIntentCookie(request *http.Request) (*http.Cookie, error) {
	if request == nil {
		return nil, errOAuthFirstLoginIntentInvalid
	}
	var result *http.Cookie
	for _, cookie := range request.Cookies() {
		if cookie.Name != OAuthFirstLoginIntentCookieName {
			continue
		}
		if result != nil || cookie.Value == "" ||
			cookie.Value != strings.TrimSpace(cookie.Value) {
			return nil, errOAuthFirstLoginIntentInvalid
		}
		copyCookie := *cookie
		result = &copyCookie
	}
	if result == nil {
		return nil, errOAuthFirstLoginIntentInvalid
	}
	return result, nil
}

func validOAuthFirstLoginIntentIssue(issue OAuthFirstLoginIntentIssue) bool {
	return issue.Purpose == OAuthPurposeFirstLogin &&
		validOAuthFirstLoginHandle(issue.IntentID, 256) &&
		validOAuthFirstLoginHandle(issue.Provider, 64) &&
		issue.Provider == strings.ToLower(issue.Provider) &&
		validOAuthFirstLoginHandle(issue.OrganizationID, 256) &&
		validOAuthFirstLoginHandle(issue.ProjectID, 256) &&
		validOAuthFirstLoginHandle(issue.StateHash, 128)
}

func validOAuthFirstLoginIntentValidation(
	expected OAuthFirstLoginIntentValidation,
) bool {
	return validOAuthFirstLoginIntentIssue(OAuthFirstLoginIntentIssue{
		IntentID:       expected.IntentID,
		Provider:       expected.Provider,
		Purpose:        expected.Purpose,
		OrganizationID: expected.OrganizationID,
		ProjectID:      expected.ProjectID,
		StateHash:      expected.StateHash,
		ExpiresAt:      time.Unix(1, 0),
	})
}

func oauthFirstLoginCallbackOrigin(request *http.Request) (string, error) {
	if request == nil || request.Host == "" || request.Host != strings.TrimSpace(request.Host) ||
		strings.ContainsAny(request.Host, "\x00\r\n\t") {
		return "", errOAuthFirstLoginIntentInvalid
	}
	return "https://" + strings.ToLower(request.Host), nil
}

var _ OAuthFirstLoginIntentTransport = (*IdentitySessionCookieTransport)(nil)
