package ashrclone

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

const (
	maxOAuthOpaqueVaultSecretBytes   = 1024 * 1024
	maxOAuthOpaqueVaultResponseBytes = (maxOAuthOpaqueVaultSecretBytes * 4 / 3) + 4096
)

var oauthOpaqueVaultNamespacePattern = regexp.MustCompile(
	`^[a-z][a-z0-9_-]{1,31}(?:\.[a-z][a-z0-9_-]{0,63}){2,7}$`,
)

type HTTPOAuthOpaqueVaultOptions struct {
	PutEndpoint     string
	GetEndpoint     string
	BindingEndpoint string
	DeleteEndpoint  string
	Client          *http.Client
	Timeout         time.Duration
}

// HTTPOAuthOpaqueVault keeps OAuth transaction and token material behind a
// caller-authenticated HTTPS client. The adapter never accepts redirects and
// never includes an upstream response body in a returned error.
type HTTPOAuthOpaqueVault struct {
	putEndpoint     string
	getEndpoint     string
	bindingEndpoint string
	deleteEndpoint  string
	client          *http.Client
	timeout         time.Duration
}

func NewHTTPOAuthOpaqueVault(
	options HTTPOAuthOpaqueVaultOptions,
) (*HTTPOAuthOpaqueVault, error) {
	if options.Client == nil {
		return nil, errors.New("OAuth opaque vault authenticated client is required")
	}
	endpoints := []*string{
		&options.PutEndpoint,
		&options.GetEndpoint,
		&options.BindingEndpoint,
		&options.DeleteEndpoint,
	}
	for _, endpoint := range endpoints {
		validated, err := strictOAuthOpaqueVaultEndpoint(*endpoint)
		if err != nil {
			return nil, err
		}
		*endpoint = validated
	}
	if options.Timeout < time.Millisecond || options.Timeout > 30*time.Second {
		return nil, errors.New("OAuth opaque vault timeout must be between 1ms and 30s")
	}
	client := *options.Client
	client.CheckRedirect = func(*http.Request, []*http.Request) error {
		return errors.New("OAuth opaque vault redirect refused")
	}
	return &HTTPOAuthOpaqueVault{
		putEndpoint: options.PutEndpoint, getEndpoint: options.GetEndpoint,
		bindingEndpoint: options.BindingEndpoint, deleteEndpoint: options.DeleteEndpoint,
		client: &client, timeout: options.Timeout,
	}, nil
}

func (vault *HTTPOAuthOpaqueVault) Put(
	ctx context.Context,
	namespace string,
	binding OAuthSecretBinding,
	secret []byte,
) (string, error) {
	if vault == nil || vault.client == nil || ctx == nil ||
		!oauthOpaqueVaultNamespacePattern.MatchString(namespace) ||
		validatePostgresOAuthBinding(binding) != nil ||
		len(secret) < 1 || len(secret) > maxOAuthOpaqueVaultSecretBytes {
		return "", errors.New("OAuth opaque vault put request is invalid")
	}
	responseBody, err := vault.postJSON(ctx, vault.putEndpoint, struct {
		Namespace    string             `json:"namespace"`
		Binding      OAuthSecretBinding `json:"binding"`
		SecretBase64 string             `json:"secret_base64"`
	}{
		Namespace: namespace, Binding: binding,
		SecretBase64: base64.StdEncoding.EncodeToString(secret),
	}, http.StatusOK, http.StatusCreated)
	if err != nil {
		return "", err
	}
	defer clear(responseBody)
	var response struct {
		OpaqueRef string `json:"opaque_ref"`
	}
	if err := decodeStrictOAuthOpaqueVaultJSON(responseBody, &response); err != nil ||
		!isOAuthOpaqueReference(response.OpaqueRef) {
		return "", errors.New("OAuth opaque vault put response is invalid")
	}
	return response.OpaqueRef, nil
}

func (vault *HTTPOAuthOpaqueVault) Get(
	ctx context.Context,
	opaqueRef string,
) ([]byte, error) {
	if vault == nil || vault.client == nil || ctx == nil ||
		!isOAuthOpaqueReference(opaqueRef) {
		return nil, errors.New("OAuth opaque vault get request is invalid")
	}
	responseBody, err := vault.postJSON(ctx, vault.getEndpoint, struct {
		OpaqueRef string `json:"opaque_ref"`
	}{OpaqueRef: opaqueRef}, http.StatusOK)
	if err != nil {
		return nil, err
	}
	defer clear(responseBody)
	var response struct {
		SecretBase64 string `json:"secret_base64"`
	}
	if err := decodeStrictOAuthOpaqueVaultJSON(responseBody, &response); err != nil ||
		response.SecretBase64 == "" {
		return nil, errors.New("OAuth opaque vault get response is invalid")
	}
	secret, err := base64.StdEncoding.Strict().DecodeString(response.SecretBase64)
	if err != nil || len(secret) < 1 || len(secret) > maxOAuthOpaqueVaultSecretBytes ||
		base64.StdEncoding.EncodeToString(secret) != response.SecretBase64 {
		clear(secret)
		return nil, errors.New("OAuth opaque vault get response is invalid")
	}
	return secret, nil
}

func (vault *HTTPOAuthOpaqueVault) Binding(
	ctx context.Context,
	opaqueRef string,
) (OAuthSecretBinding, error) {
	if vault == nil || vault.client == nil || ctx == nil ||
		!isOAuthOpaqueReference(opaqueRef) {
		return OAuthSecretBinding{}, errors.New("OAuth opaque vault binding request is invalid")
	}
	responseBody, err := vault.postJSON(ctx, vault.bindingEndpoint, struct {
		OpaqueRef string `json:"opaque_ref"`
	}{OpaqueRef: opaqueRef}, http.StatusOK)
	if err != nil {
		return OAuthSecretBinding{}, err
	}
	defer clear(responseBody)
	var binding OAuthSecretBinding
	if err := decodeStrictOAuthOpaqueVaultJSON(responseBody, &binding); err != nil ||
		validatePostgresOAuthBinding(binding) != nil {
		return OAuthSecretBinding{}, errors.New("OAuth opaque vault binding response is invalid")
	}
	return binding, nil
}

func (vault *HTTPOAuthOpaqueVault) Delete(
	ctx context.Context,
	opaqueRef string,
) error {
	if vault == nil || vault.client == nil || ctx == nil ||
		!isOAuthOpaqueReference(opaqueRef) {
		return errors.New("OAuth opaque vault delete request is invalid")
	}
	responseBody, err := vault.postJSON(ctx, vault.deleteEndpoint, struct {
		OpaqueRef string `json:"opaque_ref"`
	}{OpaqueRef: opaqueRef}, http.StatusOK, http.StatusNoContent, http.StatusNotFound)
	clear(responseBody)
	return err
}

func (vault *HTTPOAuthOpaqueVault) postJSON(
	ctx context.Context,
	endpoint string,
	payload any,
	acceptedStatuses ...int,
) ([]byte, error) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, errors.New("OAuth opaque vault request is invalid")
	}
	defer clear(encoded)
	callCtx, cancel := context.WithTimeout(ctx, vault.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		callCtx, http.MethodPost, endpoint, bytes.NewReader(encoded),
	)
	if err != nil {
		return nil, errors.New("OAuth opaque vault request is invalid")
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	response, err := vault.client.Do(request)
	if err != nil {
		return nil, safeOAuthOpaqueVaultError(err)
	}
	defer response.Body.Close()
	accepted := false
	for _, status := range acceptedStatuses {
		if response.StatusCode == status {
			accepted = true
			break
		}
	}
	if !accepted {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, maxOAuthOpaqueVaultResponseBytes))
		return nil, errors.New("OAuth opaque vault rejected the request")
	}
	if response.StatusCode == http.StatusNoContent || response.StatusCode == http.StatusNotFound {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, maxOAuthOpaqueVaultResponseBytes))
		return nil, nil
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return nil, errors.New("OAuth opaque vault response is invalid")
	}
	body, err := io.ReadAll(io.LimitReader(response.Body, maxOAuthOpaqueVaultResponseBytes+1))
	if err != nil || len(body) > maxOAuthOpaqueVaultResponseBytes {
		clear(body)
		return nil, errors.New("OAuth opaque vault response is invalid")
	}
	return body, nil
}

func strictOAuthOpaqueVaultEndpoint(raw string) (string, error) {
	if raw == "" || raw != strings.TrimSpace(raw) || strings.ContainsAny(raw, "\x00\r\n\t") {
		return "", errors.New("OAuth opaque vault endpoint must be an absolute HTTPS URL")
	}
	parsed, err := url.ParseRequestURI(raw)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" ||
		parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", errors.New("OAuth opaque vault endpoint must be an absolute HTTPS URL without query or fragment")
	}
	return parsed.String(), nil
}

func decodeStrictOAuthOpaqueVaultJSON(body []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return fmt.Errorf("OAuth opaque vault response has trailing data")
	}
	return nil
}

func safeOAuthOpaqueVaultError(err error) error {
	switch {
	case errors.Is(err, context.DeadlineExceeded):
		return fmt.Errorf("OAuth opaque vault request timed out: %w", context.DeadlineExceeded)
	case errors.Is(err, context.Canceled):
		return fmt.Errorf("OAuth opaque vault request canceled: %w", context.Canceled)
	default:
		return errors.New("OAuth opaque vault is unavailable")
	}
}

var _ OAuthOpaqueVault = (*HTTPOAuthOpaqueVault)(nil)
