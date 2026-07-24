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
	"strings"
	"time"
)

const (
	OAuthCredentialResolvePurpose    = "ashr.oauth.client_credentials.v1"
	maxOAuthCredentialReferenceBytes = 1024
	maxOAuthCredentialRequestBytes   = 16 * 1024
	maxOAuthCredentialResponseBytes  = 64 * 1024
	maxOAuthClientIDBytes            = 4096
	maxOAuthClientSecretBytes        = 16 * 1024
)

// OAuthCredentialReference names one opaque Secret Manager reference. The
// reference is safe to send to the resolver, but the material behind it must
// never be sent by the API process or stored in the repository.
type OAuthCredentialReference struct {
	ClientIDRef     string
	ClientSecretRef string
}

// HTTPOAuthCredentialsProvider resolves OAuth client material through an
// authenticated external Secret Manager. It deliberately does not cache
// responses so a provider rotation is picked up by the next OAuth operation.
type HTTPOAuthCredentialsProvider struct {
	endpoint   string
	client     *http.Client
	timeout    time.Duration
	references map[string]OAuthCredentialReference
}

type HTTPOAuthCredentialsProviderOptions struct {
	Endpoint   string
	Client     *http.Client
	Timeout    time.Duration
	References map[string]OAuthCredentialReference
}

func NewHTTPOAuthCredentialsProvider(
	options HTTPOAuthCredentialsProviderOptions,
) (*HTTPOAuthCredentialsProvider, error) {
	endpoint, err := strictOAuthCredentialEndpoint(options.Endpoint)
	if err != nil {
		return nil, err
	}
	if options.Client == nil || options.Timeout < time.Millisecond ||
		options.Timeout > 30*time.Second {
		return nil, errors.New("OAuth credential resolver configuration is invalid")
	}
	if len(options.References) == 0 || len(options.References) > 2 {
		return nil, errors.New("OAuth credential resolver references are invalid")
	}
	references := make(map[string]OAuthCredentialReference, len(options.References))
	seen := make(map[string]string, len(options.References)*2)
	for providerName, reference := range options.References {
		providerName = strings.ToLower(strings.TrimSpace(providerName))
		if providerName != "google" && providerName != "github" {
			return nil, errors.New("OAuth credential resolver provider is invalid")
		}
		if _, exists := references[providerName]; exists {
			return nil, errors.New("OAuth credential resolver provider is duplicated")
		}
		if !validOAuthCredentialReference(reference.ClientIDRef) ||
			!validOAuthCredentialReference(reference.ClientSecretRef) ||
			reference.ClientIDRef == reference.ClientSecretRef {
			return nil, errors.New("OAuth credential resolver references are invalid")
		}
		for kind, value := range map[string]string{
			"client_id":     reference.ClientIDRef,
			"client_secret": reference.ClientSecretRef,
		} {
			if _, exists := seen[value]; exists {
				return nil, errors.New("OAuth credential resolver references are duplicated")
			}
			seen[value] = providerName + "." + kind
		}
		references[providerName] = reference
	}
	client := *options.Client
	client.CheckRedirect = func(*http.Request, []*http.Request) error {
		return errors.New("OAuth credential resolver redirect refused")
	}
	return &HTTPOAuthCredentialsProvider{
		endpoint: endpoint, client: &client, timeout: options.Timeout,
		references: references,
	}, nil
}

func (provider *HTTPOAuthCredentialsProvider) OAuthCredentials(
	ctx context.Context,
	providerName string,
) (OAuthClientCredentials, error) {
	if provider == nil || provider.client == nil || ctx == nil {
		return OAuthClientCredentials{}, errors.New("OAuth credential resolver is unavailable")
	}
	providerName = strings.ToLower(strings.TrimSpace(providerName))
	reference, ok := provider.references[providerName]
	if !ok {
		return OAuthClientCredentials{}, errors.New("OAuth credentials are unavailable")
	}
	payload, err := json.Marshal(struct {
		Provider        string `json:"provider"`
		Purpose         string `json:"purpose"`
		ClientIDRef     string `json:"client_id_ref"`
		ClientSecretRef string `json:"client_secret_ref"`
	}{
		Provider:        providerName,
		Purpose:         OAuthCredentialResolvePurpose,
		ClientIDRef:     reference.ClientIDRef,
		ClientSecretRef: reference.ClientSecretRef,
	})
	if err != nil || len(payload) > maxOAuthCredentialRequestBytes {
		return OAuthClientCredentials{}, errors.New("OAuth credential resolver request is invalid")
	}
	defer clear(payload)

	callCtx, cancel := context.WithTimeout(ctx, provider.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		callCtx, http.MethodPost, provider.endpoint, bytes.NewReader(payload),
	)
	if err != nil {
		return OAuthClientCredentials{}, errors.New("OAuth credential resolver request is invalid")
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	response, err := provider.client.Do(request)
	if err != nil {
		return OAuthClientCredentials{}, safeOAuthCredentialResolverError(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, maxOAuthCredentialResponseBytes))
		return OAuthClientCredentials{}, errors.New("OAuth credential resolver rejected the request")
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return OAuthClientCredentials{}, errors.New("OAuth credential resolver response is invalid")
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maxOAuthCredentialResponseBytes+1))
	if err != nil || len(body) > maxOAuthCredentialResponseBytes {
		clear(body)
		return OAuthClientCredentials{}, errors.New("OAuth credential resolver response is invalid")
	}
	defer clear(body)
	var resolved struct {
		Provider     string `json:"provider"`
		Purpose      string `json:"purpose"`
		ClientID     string `json:"client_id"`
		ClientSecret string `json:"client_secret"`
	}
	if err := decodeStrictOAuthCredentialJSON(body, &resolved); err != nil ||
		resolved.Provider != providerName ||
		resolved.Purpose != OAuthCredentialResolvePurpose ||
		!validOAuthClientMaterial(resolved.ClientID, maxOAuthClientIDBytes) ||
		!validOAuthClientMaterial(resolved.ClientSecret, maxOAuthClientSecretBytes) ||
		resolved.ClientID == resolved.ClientSecret {
		return OAuthClientCredentials{}, errors.New("OAuth credential resolver response is invalid")
	}
	return OAuthClientCredentials{
		ClientID: resolved.ClientID, ClientSecret: resolved.ClientSecret,
	}, nil
}

func (provider *HTTPOAuthCredentialsProvider) Close() {
	if provider != nil && provider.client != nil {
		provider.client.CloseIdleConnections()
	}
}

func strictOAuthCredentialEndpoint(raw string) (string, error) {
	if raw == "" || raw != strings.TrimSpace(raw) ||
		strings.ContainsAny(raw, "\x00\r\n\t") {
		return "", errors.New("OAuth credential resolver endpoint must be an absolute HTTPS URL")
	}
	parsed, err := url.ParseRequestURI(raw)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" ||
		parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", errors.New("OAuth credential resolver endpoint must be an absolute HTTPS URL without query or fragment")
	}
	return parsed.String(), nil
}

func validOAuthCredentialReference(value string) bool {
	return len(value) >= 8 && len(value) <= maxOAuthCredentialReferenceBytes &&
		value == strings.TrimSpace(value) &&
		!strings.ContainsAny(value, "\x00\r\n\t ") &&
		(strings.HasPrefix(value, "vault:") ||
			strings.HasPrefix(value, "kms:") ||
			strings.HasPrefix(value, "secret:") ||
			strings.HasPrefix(value, "provider-ref:") ||
			strings.HasPrefix(value, "opaque-ref:"))
}

// ValidOAuthCredentialReference exposes the same conservative reference
// validation used by the HTTP adapter to production runtime configuration.
func ValidOAuthCredentialReference(value string) bool {
	return validOAuthCredentialReference(value)
}

func validOAuthClientMaterial(value string, maximum int) bool {
	return value != "" && value == strings.TrimSpace(value) &&
		len(value) <= maximum && !strings.ContainsAny(value, "\x00\r\n\t")
}

func decodeStrictOAuthCredentialJSON(body []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return fmt.Errorf("OAuth credential resolver response has trailing data")
	}
	return nil
}

func safeOAuthCredentialResolverError(err error) error {
	switch {
	case errors.Is(err, context.DeadlineExceeded):
		return fmt.Errorf("OAuth credential resolver request timed out: %w", context.DeadlineExceeded)
	case errors.Is(err, context.Canceled):
		return fmt.Errorf("OAuth credential resolver request canceled: %w", context.Canceled)
	default:
		return errors.New("OAuth credential resolver is unavailable")
	}
}

var _ OAuthCredentialsProvider = (*HTTPOAuthCredentialsProvider)(nil)
