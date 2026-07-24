package ashrclone

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const maxGitHubOAuthProviderResponseBytes = 1024 * 1024

var githubOAuthProviderExactScopes = []string{"read:user", "user:email"}

type GitHubOAuthProviderOptions struct {
	HTTPClient      *http.Client
	AuthorizeURL    string
	TokenURL        string
	APIURL          string
	UpstreamTimeout time.Duration
}

// GitHubOAuthProvider is the provider-neutral GitHub adapter used by public
// first login. GitHub is not OIDC: nonce remains encrypted in the browser and
// transaction bindings, but is deliberately never forwarded to GitHub.
type GitHubOAuthProvider struct {
	httpClient      *http.Client
	authorizeURL    string
	tokenURL        string
	apiURL          string
	upstreamTimeout time.Duration
}

func NewGitHubOAuthProvider(
	options GitHubOAuthProviderOptions,
) (*GitHubOAuthProvider, error) {
	if options.AuthorizeURL == "" {
		options.AuthorizeURL = defaultGitHubAuthorizeURL
	}
	if options.TokenURL == "" {
		options.TokenURL = defaultGitHubTokenURL
	}
	if options.APIURL == "" {
		options.APIURL = defaultGitHubAPIURL
	}
	if options.UpstreamTimeout < time.Millisecond || options.UpstreamTimeout > 60*time.Second {
		return nil, errors.New("GitHub OAuth provider timeout must be between 1ms and 60s")
	}
	authorizeURL, err := strictGitHubOAuthProviderEndpoint("authorize", options.AuthorizeURL, false)
	if err != nil {
		return nil, err
	}
	tokenURL, err := strictGitHubOAuthProviderEndpoint("token", options.TokenURL, false)
	if err != nil {
		return nil, err
	}
	apiURL, err := strictGitHubOAuthProviderEndpoint("API", options.APIURL, true)
	if err != nil {
		return nil, err
	}
	client := options.HTTPClient
	if client == nil {
		client = &http.Client{Timeout: options.UpstreamTimeout}
	}
	cloned := *client
	cloned.CheckRedirect = func(*http.Request, []*http.Request) error {
		return errors.New("GitHub OAuth redirect refused")
	}
	return &GitHubOAuthProvider{
		httpClient: &cloned, authorizeURL: authorizeURL, tokenURL: tokenURL,
		apiURL: strings.TrimRight(apiURL, "/"), upstreamTimeout: options.UpstreamTimeout,
	}, nil
}

func (*GitHubOAuthProvider) Name() string          { return "github" }
func (*GitHubOAuthProvider) SchemaVersion() string { return GitHubOAuthSchemaVersion }
func (*GitHubOAuthProvider) ExactScopes() []string {
	return append([]string(nil), githubOAuthProviderExactScopes...)
}

func (provider *GitHubOAuthProvider) AuthorizationURL(
	request OAuthAuthorizationRequest,
) (string, error) {
	if provider == nil || provider.httpClient == nil ||
		request.ClientID == "" || request.ClientID != strings.TrimSpace(request.ClientID) ||
		request.State == "" || request.State != strings.TrimSpace(request.State) ||
		request.CodeChallenge == "" || request.CodeChallenge != strings.TrimSpace(request.CodeChallenge) ||
		!validGitHubOAuthCallbackURL(request.CallbackURL) {
		return "", errors.New("GitHub authorization request is incomplete")
	}
	if err := requireExactOAuthScopes(provider.ExactScopes(), request.Scopes); err != nil {
		return "", errors.New("GitHub authorization scopes are not exact")
	}
	endpoint, err := url.Parse(provider.authorizeURL)
	if err != nil {
		return "", errors.New("GitHub authorization endpoint is invalid")
	}
	query := endpoint.Query()
	query.Set("client_id", request.ClientID)
	query.Set("redirect_uri", request.CallbackURL)
	query.Set("response_type", "code")
	query.Set("scope", strings.Join(provider.ExactScopes(), " "))
	query.Set("state", request.State)
	query.Set("code_challenge", request.CodeChallenge)
	query.Set("code_challenge_method", "S256")
	endpoint.RawQuery = query.Encode()
	return endpoint.String(), nil
}

func (provider *GitHubOAuthProvider) ExchangeCode(
	ctx context.Context,
	exchange OAuthCodeExchangeRequest,
) (OAuthTokenSet, error) {
	if provider == nil || provider.httpClient == nil || ctx == nil ||
		exchange.Credentials.ClientID == "" ||
		exchange.Credentials.ClientID != strings.TrimSpace(exchange.Credentials.ClientID) ||
		exchange.Credentials.ClientSecret == "" ||
		exchange.Credentials.ClientSecret != strings.TrimSpace(exchange.Credentials.ClientSecret) ||
		exchange.Code == "" || exchange.Code != strings.TrimSpace(exchange.Code) ||
		exchange.CodeVerifier == "" || exchange.CodeVerifier != strings.TrimSpace(exchange.CodeVerifier) ||
		!validGitHubOAuthCallbackURL(exchange.CallbackURL) {
		return OAuthTokenSet{}, provider.exchangeError(nil)
	}
	form := url.Values{
		"client_id":     {exchange.Credentials.ClientID},
		"client_secret": {exchange.Credentials.ClientSecret},
		"code":          {exchange.Code}, "redirect_uri": {exchange.CallbackURL},
		"code_verifier": {exchange.CodeVerifier},
	}
	request, cancel, err := provider.newUpstreamRequest(
		ctx, http.MethodPost, provider.tokenURL, strings.NewReader(form.Encode()),
	)
	if err != nil {
		return OAuthTokenSet{}, provider.exchangeError(err)
	}
	defer cancel()
	request.Header.Set("Accept", "application/json")
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	response, err := provider.httpClient.Do(request)
	if err != nil {
		return OAuthTokenSet{}, provider.exchangeError(err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, maxGitHubOAuthProviderResponseBytes))
		return OAuthTokenSet{}, provider.exchangeError(nil)
	}
	if !gitHubOAuthJSONResponse(response) {
		return OAuthTokenSet{}, provider.exchangeError(nil)
	}
	body, err := readBoundedGitHubOAuthProviderBody(response.Body)
	if err != nil {
		return OAuthTokenSet{}, provider.exchangeError(err)
	}
	defer clear(body)
	var payload struct {
		AccessToken string `json:"access_token"`
		TokenType   string `json:"token_type"`
		Scope       string `json:"scope"`
		Error       string `json:"error"`
	}
	if err := json.Unmarshal(body, &payload); err != nil || payload.Error != "" ||
		payload.AccessToken == "" || payload.AccessToken != strings.TrimSpace(payload.AccessToken) ||
		!strings.EqualFold(strings.TrimSpace(payload.TokenType), "bearer") {
		return OAuthTokenSet{}, provider.exchangeError(nil)
	}
	scopes := sortedUniqueStrings(githubOAuthParseScopes(payload.Scope))
	if err := requireExactOAuthScopes(provider.ExactScopes(), scopes); err != nil {
		return OAuthTokenSet{}, newOAuthPublicError(
			http.StatusBadGateway, "github_scope_mismatch",
			"GitHub granted a different OAuth scope set than requested", nil,
		)
	}
	return OAuthTokenSet{
		AccessToken: payload.AccessToken, TokenType: "bearer", Scopes: scopes,
	}, nil
}

func (provider *GitHubOAuthProvider) ResolveIdentity(
	ctx context.Context,
	request OAuthIdentityRequest,
) (OAuthProviderIdentity, error) {
	if provider == nil || provider.httpClient == nil || ctx == nil ||
		request.TokenSet.AccessToken == "" ||
		request.TokenSet.AccessToken != strings.TrimSpace(request.TokenSet.AccessToken) ||
		(request.TokenSet.TokenType != "" && !strings.EqualFold(request.TokenSet.TokenType, "bearer")) ||
		request.TokenSet.IDToken != "" ||
		requireExactOAuthScopes(provider.ExactScopes(), request.TokenSet.Scopes) != nil {
		return OAuthProviderIdentity{}, provider.identityError(nil)
	}
	var user struct {
		ID    int64  `json:"id"`
		Login string `json:"login"`
		Name  string `json:"name"`
	}
	if err := provider.apiGet(ctx, request.TokenSet.AccessToken, "/user", &user); err != nil ||
		user.ID <= 0 || user.Login == "" || user.Login != strings.TrimSpace(user.Login) {
		return OAuthProviderIdentity{}, provider.identityError(err)
	}
	var emails []struct {
		Email    string `json:"email"`
		Primary  bool   `json:"primary"`
		Verified bool   `json:"verified"`
	}
	if err := provider.apiGet(ctx, request.TokenSet.AccessToken, "/user/emails", &emails); err != nil {
		return OAuthProviderIdentity{}, provider.identityError(err)
	}
	primaryEmail := ""
	for _, candidate := range emails {
		if !candidate.Primary || !candidate.Verified {
			continue
		}
		normalized, err := normalizeIdentityEmail(candidate.Email)
		if err != nil || normalized != candidate.Email {
			return OAuthProviderIdentity{}, provider.identityError(err)
		}
		if primaryEmail != "" && primaryEmail != normalized {
			return OAuthProviderIdentity{}, provider.identityError(nil)
		}
		primaryEmail = normalized
	}
	if primaryEmail == "" {
		return OAuthProviderIdentity{}, provider.identityError(nil)
	}
	displayName := strings.TrimSpace(user.Name)
	if displayName == "" {
		displayName = user.Login
	}
	return OAuthProviderIdentity{
		Subject:     "github:" + strconv.FormatInt(user.ID, 10),
		DisplayName: displayName, Email: primaryEmail, EmailVerified: true,
	}, nil
}

func (provider *GitHubOAuthProvider) RevokeToken(
	ctx context.Context,
	credentials OAuthClientCredentials,
	token string,
) error {
	if provider == nil || provider.httpClient == nil || ctx == nil ||
		credentials.ClientID == "" || credentials.ClientID != strings.TrimSpace(credentials.ClientID) ||
		credentials.ClientSecret == "" || credentials.ClientSecret != strings.TrimSpace(credentials.ClientSecret) ||
		token == "" || token != strings.TrimSpace(token) {
		return provider.revokeError(nil)
	}
	payload, err := json.Marshal(struct {
		AccessToken string `json:"access_token"`
	}{AccessToken: token})
	if err != nil {
		return provider.revokeError(err)
	}
	defer clear(payload)
	endpoint := provider.apiURL + "/applications/" + url.PathEscape(credentials.ClientID) + "/token"
	request, cancel, err := provider.newUpstreamRequest(
		ctx, http.MethodDelete, endpoint, bytes.NewReader(payload),
	)
	if err != nil {
		return provider.revokeError(err)
	}
	defer cancel()
	request.SetBasicAuth(credentials.ClientID, credentials.ClientSecret)
	request.Header.Set("Accept", "application/vnd.github+json")
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	response, err := provider.httpClient.Do(request)
	if err != nil {
		return provider.revokeError(err)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, maxGitHubOAuthProviderResponseBytes))
	if response.StatusCode != http.StatusNoContent {
		return provider.revokeError(nil)
	}
	return nil
}

func (provider *GitHubOAuthProvider) apiGet(
	ctx context.Context,
	token string,
	path string,
	target any,
) error {
	request, cancel, err := provider.newUpstreamRequest(
		ctx, http.MethodGet, provider.apiURL+path, nil,
	)
	if err != nil {
		return err
	}
	defer cancel()
	request.Header.Set("Accept", "application/vnd.github+json")
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	response, err := provider.httpClient.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, maxGitHubOAuthProviderResponseBytes))
		return errors.New("GitHub identity lookup failed")
	}
	if !gitHubOAuthJSONResponse(response) {
		return errors.New("GitHub identity lookup failed")
	}
	body, err := readBoundedGitHubOAuthProviderBody(response.Body)
	if err != nil {
		return err
	}
	defer clear(body)
	if err := json.Unmarshal(body, target); err != nil {
		return errors.New("GitHub identity lookup failed")
	}
	return nil
}

func (provider *GitHubOAuthProvider) newUpstreamRequest(
	ctx context.Context,
	method string,
	endpoint string,
	body io.Reader,
) (*http.Request, context.CancelFunc, error) {
	upstreamContext, cancel := context.WithTimeout(ctx, provider.upstreamTimeout)
	request, err := http.NewRequestWithContext(upstreamContext, method, endpoint, body)
	if err != nil {
		cancel()
		return nil, func() {}, errors.New("GitHub OAuth upstream request is invalid")
	}
	return request, cancel, nil
}

func strictGitHubOAuthProviderEndpoint(
	name string,
	raw string,
	requireRootPath bool,
) (string, error) {
	if raw == "" || raw != strings.TrimSpace(raw) || strings.ContainsAny(raw, "\x00\r\n\t") {
		return "", fmt.Errorf("GitHub OAuth %s endpoint is invalid", name)
	}
	endpoint, err := validateOAuthEndpoint("GitHub", name, raw)
	if err != nil || endpoint.RawQuery != "" ||
		(requireRootPath && endpoint.EscapedPath() != "" && endpoint.EscapedPath() != "/") {
		return "", fmt.Errorf("GitHub OAuth %s endpoint is invalid", name)
	}
	return endpoint.String(), nil
}

func validGitHubOAuthCallbackURL(raw string) bool {
	if raw == "" || raw != strings.TrimSpace(raw) || strings.ContainsAny(raw, "\x00\r\n\t") {
		return false
	}
	endpoint, err := validateOAuthEndpoint("GitHub", "callback", raw)
	return err == nil && endpoint.RawQuery == ""
}

func gitHubOAuthJSONResponse(response *http.Response) bool {
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	return err == nil && mediaType == "application/json"
}

func readBoundedGitHubOAuthProviderBody(reader io.Reader) ([]byte, error) {
	body, err := io.ReadAll(io.LimitReader(reader, maxGitHubOAuthProviderResponseBytes+1))
	if err != nil || len(body) > maxGitHubOAuthProviderResponseBytes {
		clear(body)
		return nil, errors.New("GitHub OAuth upstream response is invalid")
	}
	return body, nil
}

func (*GitHubOAuthProvider) exchangeError(cause error) OAuthError {
	return newOAuthPublicError(
		http.StatusBadGateway, "github_token_exchange_failed",
		"GitHub token exchange failed", cause,
	)
}

func (*GitHubOAuthProvider) identityError(cause error) OAuthError {
	return newOAuthPublicError(
		http.StatusBadGateway, "github_identity_validation_failed",
		"GitHub identity validation failed", cause,
	)
}

func (*GitHubOAuthProvider) revokeError(cause error) OAuthError {
	return newOAuthPublicError(
		http.StatusBadGateway, "github_token_revoke_failed",
		"GitHub token revocation failed; the local connection was retained", cause,
	)
}

var _ OAuthProviderAdapter = (*GitHubOAuthProvider)(nil)
