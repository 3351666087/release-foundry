package releasefoundry

import (
	"context"
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"math/big"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const (
	GoogleOAuthSchemaVersion = "releasefoundry.google_oauth.v1"

	defaultGoogleAuthorizeURL = "https://accounts.google.com/o/oauth2/v2/auth"
	defaultGoogleTokenURL     = "https://oauth2.googleapis.com/token"
	defaultGoogleRevokeURL    = "https://oauth2.googleapis.com/revoke"
	defaultGoogleJWKSURL      = "https://www.googleapis.com/oauth2/v3/certs"
)

var defaultGoogleIssuers = []string{"accounts.google.com", "https://accounts.google.com"}
var defaultGoogleScopes = []string{"email", "openid", "profile"}

type GoogleOIDCOptions struct {
	HTTPClient       OAuthHTTPClient
	AuthorizeURL     string
	TokenURL         string
	RevokeURL        string
	JWKSURL          string
	Issuers          []string
	UpstreamTimeout  time.Duration
	ClockSkew        time.Duration
	MaxTokenLifetime time.Duration
}

type GoogleOIDCProvider struct {
	httpClient       OAuthHTTPClient
	authorizeURL     string
	tokenURL         string
	revokeURL        string
	jwksURL          string
	issuers          []string
	upstreamTimeout  time.Duration
	clockSkew        time.Duration
	maxTokenLifetime time.Duration
}

func NewGoogleOIDCProvider(options GoogleOIDCOptions) (*GoogleOIDCProvider, error) {
	if options.HTTPClient == nil {
		options.HTTPClient = &http.Client{Timeout: 15 * time.Second}
	}
	if options.AuthorizeURL == "" {
		options.AuthorizeURL = defaultGoogleAuthorizeURL
	}
	if options.TokenURL == "" {
		options.TokenURL = defaultGoogleTokenURL
	}
	if options.RevokeURL == "" {
		options.RevokeURL = defaultGoogleRevokeURL
	}
	if options.JWKSURL == "" {
		options.JWKSURL = defaultGoogleJWKSURL
	}
	for name, endpoint := range map[string]string{
		"authorize": options.AuthorizeURL, "token": options.TokenURL, "revoke": options.RevokeURL, "jwks": options.JWKSURL,
	} {
		if _, err := validateOAuthEndpoint("Google", name, endpoint); err != nil {
			return nil, err
		}
	}
	if len(options.Issuers) == 0 {
		options.Issuers = append([]string(nil), defaultGoogleIssuers...)
	}
	for _, issuer := range options.Issuers {
		if issuer != "accounts.google.com" {
			if _, err := validateOAuthEndpoint("Google", "issuer", issuer); err != nil {
				return nil, err
			}
		}
	}
	if options.UpstreamTimeout <= 0 {
		options.UpstreamTimeout = 10 * time.Second
	}
	if options.ClockSkew <= 0 {
		options.ClockSkew = 30 * time.Second
	}
	if options.MaxTokenLifetime <= 0 {
		options.MaxTokenLifetime = 2 * time.Hour
	}
	return &GoogleOIDCProvider{
		httpClient: options.HTTPClient, authorizeURL: strings.TrimSpace(options.AuthorizeURL),
		tokenURL: strings.TrimSpace(options.TokenURL), revokeURL: strings.TrimSpace(options.RevokeURL),
		jwksURL: strings.TrimSpace(options.JWKSURL), issuers: sortedUniqueStrings(options.Issuers),
		upstreamTimeout: options.UpstreamTimeout, clockSkew: options.ClockSkew, maxTokenLifetime: options.MaxTokenLifetime,
	}, nil
}

func (provider *GoogleOIDCProvider) Name() string          { return "google" }
func (provider *GoogleOIDCProvider) SchemaVersion() string { return GoogleOAuthSchemaVersion }
func (provider *GoogleOIDCProvider) ExactScopes() []string {
	return append([]string(nil), defaultGoogleScopes...)
}

func (provider *GoogleOIDCProvider) AuthorizationURL(request OAuthAuthorizationRequest) (string, error) {
	if strings.TrimSpace(request.ClientID) == "" || strings.TrimSpace(request.CallbackURL) == "" ||
		strings.TrimSpace(request.State) == "" || strings.TrimSpace(request.CodeChallenge) == "" ||
		strings.TrimSpace(request.Nonce) == "" {
		return "", fmt.Errorf("Google authorization request is incomplete")
	}
	if err := requireExactOAuthScopes(provider.ExactScopes(), request.Scopes); err != nil {
		return "", fmt.Errorf("Google authorization scopes are not exact: %w", err)
	}
	endpoint, err := url.Parse(provider.authorizeURL)
	if err != nil {
		return "", err
	}
	query := endpoint.Query()
	query.Set("client_id", request.ClientID)
	query.Set("redirect_uri", request.CallbackURL)
	query.Set("response_type", "code")
	query.Set("scope", strings.Join(provider.ExactScopes(), " "))
	query.Set("state", request.State)
	query.Set("nonce", request.Nonce)
	query.Set("code_challenge", request.CodeChallenge)
	query.Set("code_challenge_method", "S256")
	endpoint.RawQuery = query.Encode()
	return endpoint.String(), nil
}

func (provider *GoogleOIDCProvider) ExchangeCode(ctx context.Context, exchange OAuthCodeExchangeRequest) (OAuthTokenSet, error) {
	form := url.Values{
		"client_id": {exchange.Credentials.ClientID}, "client_secret": {exchange.Credentials.ClientSecret},
		"code": {exchange.Code}, "redirect_uri": {exchange.CallbackURL},
		"code_verifier": {exchange.CodeVerifier}, "grant_type": {"authorization_code"},
	}
	request, cancel, err := provider.newUpstreamRequest(ctx, http.MethodPost, provider.tokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return OAuthTokenSet{}, newOAuthPublicError(http.StatusBadGateway, "google_token_exchange_failed", "Google token exchange failed", err)
	}
	defer cancel()
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	response, err := provider.httpClient.Do(request)
	if err != nil {
		return OAuthTokenSet{}, newOAuthPublicError(http.StatusBadGateway, "google_token_exchange_failed", "Google token exchange failed", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	if err != nil {
		return OAuthTokenSet{}, newOAuthPublicError(http.StatusBadGateway, "google_token_exchange_failed", "Google token exchange failed", err)
	}
	var payload struct {
		AccessToken string `json:"access_token"`
		TokenType   string `json:"token_type"`
		Scope       string `json:"scope"`
		IDToken     string `json:"id_token"`
		Error       string `json:"error"`
	}
	if err := json.Unmarshal(body, &payload); err != nil || response.StatusCode < 200 || response.StatusCode >= 300 ||
		payload.Error != "" || strings.TrimSpace(payload.AccessToken) == "" || strings.TrimSpace(payload.IDToken) == "" ||
		!strings.EqualFold(strings.TrimSpace(payload.TokenType), "bearer") {
		return OAuthTokenSet{}, newOAuthPublicError(http.StatusBadGateway, "google_token_exchange_failed", "Google token exchange failed", nil)
	}
	scopes, err := normalizeGoogleGrantedScopes(parseSpaceSeparatedScopes(payload.Scope))
	if err != nil {
		return OAuthTokenSet{}, newOAuthPublicError(http.StatusBadGateway, "google_scope_mismatch", "Google granted a different OAuth scope set than requested", err)
	}
	if err := requireExactOAuthScopes(provider.ExactScopes(), scopes); err != nil {
		return OAuthTokenSet{}, newOAuthPublicError(http.StatusBadGateway, "google_scope_mismatch", "Google granted a different OAuth scope set than requested", err)
	}
	return OAuthTokenSet{
		AccessToken: payload.AccessToken, TokenType: payload.TokenType, Scopes: scopes, IDToken: payload.IDToken,
	}, nil
}

func normalizeGoogleGrantedScopes(scopes []string) ([]string, error) {
	canonical := make([]string, 0, len(scopes))
	for _, scope := range scopes {
		switch scope {
		case "openid":
			canonical = append(canonical, "openid")
		case "email", "https://www.googleapis.com/auth/userinfo.email":
			canonical = append(canonical, "email")
		case "profile", "https://www.googleapis.com/auth/userinfo.profile":
			canonical = append(canonical, "profile")
		default:
			return nil, fmt.Errorf("unexpected Google scope")
		}
	}
	return sortedUniqueStrings(canonical), nil
}

func (provider *GoogleOIDCProvider) ResolveIdentity(ctx context.Context, request OAuthIdentityRequest) (OAuthProviderIdentity, error) {
	header, claims, signingInput, signature, err := parseGoogleIDToken(request.TokenSet.IDToken)
	if err != nil {
		return OAuthProviderIdentity{}, provider.identityError(err)
	}
	if header.Alg != "RS256" || strings.TrimSpace(header.Kid) == "" {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("unsupported ID token header"))
	}
	key, err := provider.fetchSigningKey(ctx, header.Kid)
	if err != nil {
		return OAuthProviderIdentity{}, provider.identityError(err)
	}
	digest := sha256.Sum256([]byte(signingInput))
	if err := rsa.VerifyPKCS1v15(key, crypto.SHA256, digest[:], signature); err != nil {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("ID token signature is invalid"))
	}
	now := request.Now.UTC()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	if !oauthContainsString(provider.issuers, claims.Issuer) {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("ID token issuer is invalid"))
	}
	if !claims.Audience.Contains(request.ClientID) || len(claims.Audience.Values()) != 1 {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("ID token audience is invalid"))
	}
	if strings.TrimSpace(claims.Subject) == "" || strings.TrimSpace(claims.Nonce) == "" || claims.Nonce != request.Nonce {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("ID token subject or nonce is invalid"))
	}
	if claims.ExpiresAt <= 0 || !now.Before(time.Unix(claims.ExpiresAt, 0).Add(provider.clockSkew)) {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("ID token is expired"))
	}
	if claims.IssuedAt <= 0 || time.Unix(claims.IssuedAt, 0).After(now.Add(provider.clockSkew)) {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("ID token issued-at is invalid"))
	}
	if time.Unix(claims.ExpiresAt, 0).Sub(time.Unix(claims.IssuedAt, 0)) > provider.maxTokenLifetime {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("ID token lifetime is invalid"))
	}
	if claims.NotBefore > 0 && now.Add(provider.clockSkew).Before(time.Unix(claims.NotBefore, 0)) {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("ID token is not active"))
	}
	if strings.TrimSpace(claims.Email) == "" || !claims.EmailVerified {
		return OAuthProviderIdentity{}, provider.identityError(fmt.Errorf("Google account email is absent or unverified"))
	}
	return OAuthProviderIdentity{
		Subject: claims.Subject, DisplayName: strings.TrimSpace(claims.Name),
		Email: strings.TrimSpace(claims.Email), EmailVerified: true,
	}, nil
}

func (provider *GoogleOIDCProvider) RevokeToken(ctx context.Context, _ OAuthClientCredentials, token string) error {
	form := url.Values{"token": {token}}
	request, cancel, err := provider.newUpstreamRequest(ctx, http.MethodPost, provider.revokeURL, strings.NewReader(form.Encode()))
	if err != nil {
		return newOAuthPublicError(http.StatusBadGateway, "google_token_revoke_failed", "Google token revocation failed; the local connection was retained", err)
	}
	defer cancel()
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	response, err := provider.httpClient.Do(request)
	if err != nil {
		return newOAuthPublicError(http.StatusBadGateway, "google_token_revoke_failed", "Google token revocation failed; the local connection was retained", err)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1<<20))
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return newOAuthPublicError(http.StatusBadGateway, "google_token_revoke_failed", "Google token revocation failed; the local connection was retained", nil)
	}
	return nil
}

func (provider *GoogleOIDCProvider) newUpstreamRequest(ctx context.Context, method, endpoint string, body io.Reader) (*http.Request, context.CancelFunc, error) {
	upstreamContext, cancel := context.WithTimeout(ctx, provider.upstreamTimeout)
	request, err := http.NewRequestWithContext(upstreamContext, method, endpoint, body)
	if err != nil {
		cancel()
		return nil, func() {}, err
	}
	return request, cancel, nil
}

func (provider *GoogleOIDCProvider) fetchSigningKey(ctx context.Context, kid string) (*rsa.PublicKey, error) {
	request, cancel, err := provider.newUpstreamRequest(ctx, http.MethodGet, provider.jwksURL, nil)
	if err != nil {
		return nil, err
	}
	defer cancel()
	request.Header.Set("Accept", "application/json")
	response, err := provider.httpClient.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1<<20))
		return nil, fmt.Errorf("Google JWKS lookup failed")
	}
	var document struct {
		Keys []struct {
			Kid string `json:"kid"`
			Kty string `json:"kty"`
			Alg string `json:"alg"`
			Use string `json:"use"`
			N   string `json:"n"`
			E   string `json:"e"`
		} `json:"keys"`
	}
	if err := json.NewDecoder(io.LimitReader(response.Body, 1<<20)).Decode(&document); err != nil {
		return nil, err
	}
	for _, candidate := range document.Keys {
		if candidate.Kid != kid || candidate.Kty != "RSA" || candidate.Alg != "RS256" || (candidate.Use != "" && candidate.Use != "sig") {
			continue
		}
		modulus, err := base64.RawURLEncoding.DecodeString(candidate.N)
		if err != nil {
			return nil, err
		}
		exponentBytes, err := base64.RawURLEncoding.DecodeString(candidate.E)
		if err != nil || len(exponentBytes) == 0 || len(exponentBytes) > 4 {
			return nil, fmt.Errorf("Google JWKS exponent is invalid")
		}
		exponent := 0
		for _, value := range exponentBytes {
			exponent = exponent<<8 | int(value)
		}
		if exponent < 3 || exponent%2 == 0 {
			return nil, fmt.Errorf("Google JWKS exponent is invalid")
		}
		key := &rsa.PublicKey{N: new(big.Int).SetBytes(modulus), E: exponent}
		if key.N.BitLen() < 2048 {
			return nil, fmt.Errorf("Google JWKS key is too small")
		}
		return key, nil
	}
	return nil, fmt.Errorf("Google JWKS signing key was not found")
}

func (provider *GoogleOIDCProvider) identityError(cause error) OAuthError {
	return newOAuthPublicError(http.StatusBadGateway, "google_identity_validation_failed", "Google identity validation failed", cause)
}

type googleJWTHeader struct {
	Alg string `json:"alg"`
	Kid string `json:"kid"`
	Typ string `json:"typ"`
}

type googleAudience []string

func (audience *googleAudience) UnmarshalJSON(value []byte) error {
	var single string
	if err := json.Unmarshal(value, &single); err == nil {
		*audience = googleAudience{single}
		return nil
	}
	var multiple []string
	if err := json.Unmarshal(value, &multiple); err != nil {
		return err
	}
	*audience = googleAudience(multiple)
	return nil
}

func (audience googleAudience) Contains(candidate string) bool {
	return oauthContainsString(audience, candidate)
}
func (audience googleAudience) Values() []string { return append([]string(nil), audience...) }

type googleIDTokenClaims struct {
	Issuer        string         `json:"iss"`
	Audience      googleAudience `json:"aud"`
	Subject       string         `json:"sub"`
	ExpiresAt     int64          `json:"exp"`
	IssuedAt      int64          `json:"iat"`
	NotBefore     int64          `json:"nbf"`
	Nonce         string         `json:"nonce"`
	Email         string         `json:"email"`
	EmailVerified bool           `json:"email_verified"`
	Name          string         `json:"name"`
}

func parseGoogleIDToken(token string) (googleJWTHeader, googleIDTokenClaims, string, []byte, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 || len(parts[0]) > 8<<10 || len(parts[1]) > 64<<10 || len(parts[2]) > 16<<10 {
		return googleJWTHeader{}, googleIDTokenClaims{}, "", nil, fmt.Errorf("ID token is malformed")
	}
	headerBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return googleJWTHeader{}, googleIDTokenClaims{}, "", nil, err
	}
	claimBytes, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return googleJWTHeader{}, googleIDTokenClaims{}, "", nil, err
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return googleJWTHeader{}, googleIDTokenClaims{}, "", nil, err
	}
	var header googleJWTHeader
	var claims googleIDTokenClaims
	if err := json.Unmarshal(headerBytes, &header); err != nil {
		return googleJWTHeader{}, googleIDTokenClaims{}, "", nil, err
	}
	if err := json.Unmarshal(claimBytes, &claims); err != nil {
		return googleJWTHeader{}, googleIDTokenClaims{}, "", nil, err
	}
	return header, claims, parts[0] + "." + parts[1], signature, nil
}

func oauthContainsString[T ~string](values []T, candidate string) bool {
	for _, value := range values {
		if string(value) == candidate {
			return true
		}
	}
	return false
}
