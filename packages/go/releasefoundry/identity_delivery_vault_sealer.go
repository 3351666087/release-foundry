package releasefoundry

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

const maxIdentityDeliveryVaultSealerResponseBytes = 4 * 1024

type HTTPIdentityDeliveryVaultSealerOptions struct {
	SealEndpoint   string
	DeleteEndpoint string
	Client         *http.Client
	Timeout        time.Duration
}

// HTTPIdentityDeliveryVaultSealer sends secret material only through a
// caller-injected authenticated client. TLS, mTLS, and workload-signing
// configuration remain the caller's responsibility.
type HTTPIdentityDeliveryVaultSealer struct {
	sealEndpoint   string
	deleteEndpoint string
	client         *http.Client
	timeout        time.Duration
}

func NewHTTPIdentityDeliveryVaultSealer(
	options HTTPIdentityDeliveryVaultSealerOptions,
) (*HTTPIdentityDeliveryVaultSealer, error) {
	if options.Client == nil {
		return nil, errors.New("identity delivery vault authenticated client is required")
	}
	sealEndpoint, err := strictIdentityDeliveryVaultEndpoint(options.SealEndpoint)
	if err != nil {
		return nil, err
	}
	deleteEndpoint, err := strictIdentityDeliveryVaultEndpoint(options.DeleteEndpoint)
	if err != nil {
		return nil, err
	}
	if options.Timeout < time.Millisecond || options.Timeout > 30*time.Second {
		return nil, errors.New("identity delivery vault timeout must be between 1ms and 30s")
	}
	client := *options.Client
	client.CheckRedirect = func(*http.Request, []*http.Request) error {
		return errors.New("identity delivery vault redirect refused")
	}
	return &HTTPIdentityDeliveryVaultSealer{
		sealEndpoint: sealEndpoint, deleteEndpoint: deleteEndpoint,
		client: &client, timeout: options.Timeout,
	}, nil
}

func (sealer *HTTPIdentityDeliveryVaultSealer) SealIdentityDelivery(
	ctx context.Context,
	request IdentityDeliverySealRequest,
) (string, error) {
	if sealer == nil || sealer.client == nil || validateIdentityDeliverySealRequest(request) != nil {
		return "", errors.New("identity delivery vault seal request is invalid")
	}
	responseBody, err := sealer.postJSON(ctx, sealer.sealEndpoint, struct {
		ReservationID   string                      `json:"reservation_id"`
		TenantID        string                      `json:"tenant_id"`
		ProjectID       string                      `json:"project_id"`
		ChallengeHandle string                      `json:"challenge_handle"`
		Channel         IdentityVerificationChannel `json:"channel"`
		Purpose         IdentityVerificationPurpose `json:"purpose"`
		Destination     string                      `json:"destination"`
		Code            string                      `json:"code"`
		ExpiresAt       time.Time                   `json:"expires_at"`
	}{
		ReservationID: request.ReservationID, TenantID: request.TenantID,
		ProjectID: request.ProjectID, ChallengeHandle: request.ChallengeHandle,
		Channel: request.Channel, Purpose: request.Purpose,
		Destination: request.Destination, Code: request.Code,
		ExpiresAt: request.ExpiresAt.UTC(),
	}, http.StatusOK, http.StatusCreated)
	if err != nil {
		return "", err
	}
	defer clear(responseBody)
	var response struct {
		OpaqueRef string `json:"opaque_ref"`
	}
	if err := decodeStrictIdentityDeliveryVaultJSON(responseBody, &response); err != nil ||
		!identityDeliveryOpaqueReferencePattern.MatchString(response.OpaqueRef) {
		return "", errors.New("identity delivery vault seal response is invalid")
	}
	return response.OpaqueRef, nil
}

func (sealer *HTTPIdentityDeliveryVaultSealer) DeleteIdentityDelivery(
	ctx context.Context,
	opaqueRef string,
) error {
	if sealer == nil || sealer.client == nil ||
		!identityDeliveryOpaqueReferencePattern.MatchString(opaqueRef) {
		return errors.New("identity delivery vault delete request is invalid")
	}
	responseBody, err := sealer.postJSON(ctx, sealer.deleteEndpoint, struct {
		OpaqueRef string `json:"opaque_ref"`
	}{OpaqueRef: opaqueRef}, http.StatusOK, http.StatusNoContent, http.StatusNotFound)
	clear(responseBody)
	return err
}

func (sealer *HTTPIdentityDeliveryVaultSealer) postJSON(
	ctx context.Context,
	endpoint string,
	payload any,
	acceptedStatuses ...int,
) ([]byte, error) {
	if ctx == nil {
		return nil, errors.New("identity delivery vault context is required")
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, errors.New("identity delivery vault request is invalid")
	}
	defer clear(encoded)
	callCtx, cancel := context.WithTimeout(ctx, sealer.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		callCtx, http.MethodPost, endpoint, bytes.NewReader(encoded),
	)
	if err != nil {
		return nil, errors.New("identity delivery vault request is invalid")
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	response, err := sealer.client.Do(request)
	if err != nil {
		return nil, safeIdentityDeliveryVaultError(err)
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
		_, _ = io.Copy(io.Discard, io.LimitReader(
			response.Body, maxIdentityDeliveryVaultSealerResponseBytes,
		))
		return nil, errors.New("identity delivery vault rejected the request")
	}
	if response.StatusCode == http.StatusNoContent || response.StatusCode == http.StatusNotFound {
		_, _ = io.Copy(io.Discard, io.LimitReader(
			response.Body, maxIdentityDeliveryVaultSealerResponseBytes,
		))
		return nil, nil
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return nil, errors.New("identity delivery vault response is invalid")
	}
	body, err := io.ReadAll(io.LimitReader(
		response.Body, maxIdentityDeliveryVaultSealerResponseBytes+1,
	))
	if err != nil || len(body) > maxIdentityDeliveryVaultSealerResponseBytes {
		clear(body)
		return nil, errors.New("identity delivery vault response is invalid")
	}
	return body, nil
}

func strictIdentityDeliveryVaultEndpoint(raw string) (string, error) {
	raw = strings.TrimSpace(raw)
	parsed, err := url.ParseRequestURI(raw)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" ||
		parsed.User != nil || parsed.Fragment != "" {
		return "", errors.New("identity delivery vault endpoint must be an absolute HTTPS URL")
	}
	return parsed.String(), nil
}

func decodeStrictIdentityDeliveryVaultJSON(body []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return fmt.Errorf("identity delivery vault response has trailing data")
	}
	return nil
}

func safeIdentityDeliveryVaultError(err error) error {
	switch {
	case errors.Is(err, context.DeadlineExceeded):
		return fmt.Errorf("identity delivery vault request timed out: %w", context.DeadlineExceeded)
	case errors.Is(err, context.Canceled):
		return fmt.Errorf("identity delivery vault request canceled: %w", context.Canceled)
	default:
		return errors.New("identity delivery vault is unavailable")
	}
}

var (
	_ IdentityDeliveryVaultSealer  = (*HTTPIdentityDeliveryVaultSealer)(nil)
	_ IdentityDeliveryVaultDeleter = (*HTTPIdentityDeliveryVaultSealer)(nil)
)
