package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/ashr-labs/ashr/packages/go/ashrclone"
)

const (
	maxIdentityDeliverySidecarRequestBytes   = 32 * 1024
	maxIdentityDeliverySidecarResponseBytes  = 16 * 1024
	maxIdentityDeliveryMTLSCABundleFileBytes = 1024 * 1024
	maxIdentityDeliveryMTLSIdentityFileBytes = 256 * 1024
)

var identityDeliveryRelayIdempotencyKeyPattern = regexp.MustCompile(
	`^[A-Za-z0-9][A-Za-z0-9._:-]{7,255}$`,
)
var identityDeliveryRelayAcceptanceReferencePattern = regexp.MustCompile(
	`^(provider-ref|message-ref|receipt-ref):[A-Za-z0-9][A-Za-z0-9._:/-]*$`,
)

type identityDeliveryHTTPVault struct {
	endpoint string
	client   *http.Client
	timeout  time.Duration
}

type identityDeliveryVaultRequest struct {
	OpaqueRef string `json:"opaque_ref"`
}

type identityDeliveryVaultResponse struct {
	TaskID      string                                `json:"task_id"`
	TenantID    string                                `json:"tenant_id"`
	ProjectID   string                                `json:"project_id"`
	ChallengeID string                                `json:"challenge_id"`
	Channel     ashrclone.IdentityVerificationChannel `json:"channel"`
	Destination string                                `json:"destination"`
	Code        string                                `json:"code"`
}

func (vault *identityDeliveryHTTPVault) OpenIdentityDelivery(
	ctx context.Context,
	opaqueRef string,
) (ashrclone.IdentityDeliverySecret, error) {
	if vault == nil || vault.client == nil || strings.TrimSpace(opaqueRef) == "" {
		return ashrclone.IdentityDeliverySecret{}, errors.New(
			"identity delivery vault is unavailable",
		)
	}
	callCtx, cancel, err := identityDeliverySidecarContext(ctx, vault.timeout)
	if err != nil {
		return ashrclone.IdentityDeliverySecret{}, identityDeliverySidecarFailure(
			"vault_unavailable", "identity delivery vault is unavailable", err,
		)
	}
	defer cancel()
	var response identityDeliveryVaultResponse
	if err = postIdentityDeliveryJSON(
		callCtx,
		vault.client,
		vault.endpoint,
		identityDeliveryVaultRequest{OpaqueRef: opaqueRef},
		&response,
	); err != nil {
		return ashrclone.IdentityDeliverySecret{}, identityDeliverySidecarFailure(
			"vault_unavailable", "identity delivery vault is unavailable", err,
		)
	}
	return ashrclone.IdentityDeliverySecret{
		TaskID: response.TaskID, TenantID: response.TenantID,
		ProjectID: response.ProjectID, ChallengeID: response.ChallengeID,
		Channel: response.Channel, Destination: response.Destination,
		Code: response.Code,
	}, nil
}

type identityDeliveryHTTPAdapter struct {
	endpoint string
	channel  ashrclone.IdentityVerificationChannel
	client   *http.Client
	timeout  time.Duration
}

type identityDeliveryRelayRequest struct {
	ChallengeID            string                                `json:"challenge_id"`
	Channel                ashrclone.IdentityVerificationChannel `json:"channel"`
	Destination            string                                `json:"destination"`
	Code                   string                                `json:"code"`
	Purpose                ashrclone.IdentityVerificationPurpose `json:"purpose"`
	ExpiresAt              time.Time                             `json:"expires_at"`
	ProviderIdempotencyKey string                                `json:"provider_idempotency_key"`
}

type identityDeliveryRelayResponse struct {
	ProviderAcceptanceRef string    `json:"provider_acceptance_ref"`
	AcceptedAt            time.Time `json:"accepted_at"`
}

func (adapter *identityDeliveryHTTPAdapter) SendIdentityVerification(
	ctx context.Context,
	delivery ashrclone.IdentityVerificationDelivery,
) error {
	_, err := adapter.SendIdentityVerificationWithAcceptance(ctx, delivery)
	return err
}

func (adapter *identityDeliveryHTTPAdapter) SendIdentityVerificationWithAcceptance(
	ctx context.Context,
	delivery ashrclone.IdentityVerificationDelivery,
) (ashrclone.IdentityDeliveryProviderAcceptance, error) {
	if adapter == nil || adapter.client == nil || delivery.Channel != adapter.channel ||
		!identityDeliveryRelayIdempotencyKeyPattern.MatchString(
			delivery.ProviderIdempotencyKey,
		) {
		return ashrclone.IdentityDeliveryProviderAcceptance{}, errors.New(
			"identity delivery relay is unavailable",
		)
	}
	callCtx, cancel, err := identityDeliverySidecarContext(ctx, adapter.timeout)
	if err != nil {
		return ashrclone.IdentityDeliveryProviderAcceptance{}, identityDeliverySidecarFailure(
			"relay_unavailable", "identity delivery relay is unavailable", err,
		)
	}
	defer cancel()
	request := identityDeliveryRelayRequest{
		ChallengeID: delivery.ChallengeID, Channel: delivery.Channel,
		Destination: delivery.Destination, Code: delivery.Code,
		Purpose: delivery.Purpose, ExpiresAt: delivery.ExpiresAt,
		ProviderIdempotencyKey: delivery.ProviderIdempotencyKey,
	}
	var response identityDeliveryRelayResponse
	if err = postIdentityDeliveryJSON(
		callCtx, adapter.client, adapter.endpoint, request, &response,
	); err != nil {
		return ashrclone.IdentityDeliveryProviderAcceptance{}, identityDeliverySidecarFailure(
			"relay_unavailable", "identity delivery relay is unavailable", err,
		)
	}
	if len(response.ProviderAcceptanceRef) > 256 ||
		!identityDeliveryRelayAcceptanceReferencePattern.MatchString(
			response.ProviderAcceptanceRef,
		) || response.AcceptedAt.IsZero() {
		return ashrclone.IdentityDeliveryProviderAcceptance{}, identityDeliverySidecarFailure(
			"relay_unavailable",
			"identity delivery relay is unavailable",
			errors.New("identity delivery relay acceptance is invalid"),
		)
	}
	return ashrclone.IdentityDeliveryProviderAcceptance{
		Reference:  response.ProviderAcceptanceRef,
		AcceptedAt: response.AcceptedAt.UTC(),
	}, nil
}

func newIdentityDeliveryMTLSHTTPClient(
	profile identityDeliveryMTLSFileProfile,
	timeout time.Duration,
) (*http.Client, error) {
	connectionTimeout := minIdentityDeliveryCommandDuration(2*time.Second, timeout)
	caPEM, err := readIdentityDeliveryMTLSFile(
		profile.caBundleFile, maxIdentityDeliveryMTLSCABundleFileBytes,
	)
	if err != nil {
		return nil, errors.New("identity delivery mTLS trust material is unavailable")
	}
	defer clear(caPEM)
	certificatePEM, err := readIdentityDeliveryMTLSFile(
		profile.clientCertificateFile, maxIdentityDeliveryMTLSIdentityFileBytes,
	)
	if err != nil {
		return nil, errors.New("identity delivery mTLS identity material is unavailable")
	}
	defer clear(certificatePEM)
	privateKeyPEM, err := readIdentityDeliveryMTLSFile(
		profile.clientPrivateKeyFile, maxIdentityDeliveryMTLSIdentityFileBytes,
	)
	if err != nil {
		return nil, errors.New("identity delivery mTLS identity material is unavailable")
	}
	defer clear(privateKeyPEM)
	client, err := ashrclone.NewIdentityDeliveryMTLSHTTPClient(
		ashrclone.IdentityDeliveryMTLSClientOptions{
			CABundlePEM: caPEM, ClientCertificatePEM: certificatePEM,
			ClientPrivateKeyPEM: privateKeyPEM, ServerName: profile.serverName,
			DialTimeout: connectionTimeout, TLSHandshakeTimeout: connectionTimeout,
			ResponseHeaderTimeout: timeout, RequestTimeout: timeout,
		},
	)
	if err != nil {
		return nil, errors.New("identity delivery mTLS profile was rejected")
	}
	return client, nil
}

func readIdentityDeliveryMTLSFile(path string, limit int64) ([]byte, error) {
	if strings.TrimSpace(path) == "" || limit < 1 {
		return nil, errors.New("identity delivery mTLS credential file is invalid")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, errors.New("identity delivery mTLS credential file is unavailable")
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() < 1 || info.Size() > limit {
		return nil, errors.New("identity delivery mTLS credential file is invalid")
	}
	encoded, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil || int64(len(encoded)) > limit || len(encoded) == 0 {
		clear(encoded)
		return nil, errors.New("identity delivery mTLS credential file is invalid")
	}
	return encoded, nil
}

func identityDeliverySidecarContext(
	ctx context.Context,
	timeout time.Duration,
) (context.Context, context.CancelFunc, error) {
	if ctx == nil {
		return nil, nil, errors.New("identity delivery sidecar context is required")
	}
	if timeout < time.Millisecond {
		return nil, nil, errors.New("identity delivery sidecar timeout is invalid")
	}
	bounded, cancel := context.WithTimeout(ctx, timeout)
	return bounded, cancel, nil
}

func identityDeliverySidecarFailure(code, message string, err error) error {
	var safeCause error
	switch {
	case errors.Is(err, context.DeadlineExceeded):
		safeCause = context.DeadlineExceeded
	case errors.Is(err, context.Canceled):
		safeCause = context.Canceled
	}
	return newIdentityDeliveryCommandError(code, message, safeCause)
}

func postIdentityDeliveryJSON(
	ctx context.Context,
	client *http.Client,
	endpoint string,
	requestBody any,
	responseBody any,
) error {
	if ctx == nil || client == nil || strings.TrimSpace(endpoint) == "" {
		return errors.New("identity delivery sidecar request is invalid")
	}
	encoded, err := json.Marshal(requestBody)
	if err != nil {
		return errors.New("identity delivery sidecar request is invalid")
	}
	defer clear(encoded)
	if len(encoded) > maxIdentityDeliverySidecarRequestBytes {
		return errors.New("identity delivery sidecar request is too large")
	}
	request, err := http.NewRequestWithContext(
		ctx, http.MethodPost, endpoint, bytes.NewReader(encoded),
	)
	if err != nil {
		return errors.New("identity delivery sidecar request is invalid")
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	response, err := client.Do(request)
	if err != nil {
		return identityDeliverySidecarFailure(
			"sidecar_unavailable", "identity delivery sidecar is unavailable", err,
		)
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		_, _ = io.Copy(io.Discard, io.LimitReader(
			response.Body, maxIdentityDeliverySidecarResponseBytes,
		))
		return errors.New("identity delivery sidecar rejected the request")
	}
	if responseBody == nil {
		_, _ = io.Copy(io.Discard, io.LimitReader(
			response.Body, maxIdentityDeliverySidecarResponseBytes,
		))
		return nil
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return errors.New("identity delivery sidecar response is invalid")
	}
	encodedResponse, err := io.ReadAll(io.LimitReader(
		response.Body, maxIdentityDeliverySidecarResponseBytes+1,
	))
	if err != nil || len(encodedResponse) > maxIdentityDeliverySidecarResponseBytes {
		clear(encodedResponse)
		return errors.New("identity delivery sidecar response is invalid")
	}
	defer clear(encodedResponse)
	decoder := json.NewDecoder(bytes.NewReader(encodedResponse))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(responseBody); err != nil {
		return errors.New("identity delivery sidecar response is invalid")
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("identity delivery sidecar response is invalid")
	}
	return nil
}

func minIdentityDeliveryCommandDuration(left, right time.Duration) time.Duration {
	if left < right {
		return left
	}
	return right
}

var (
	_ ashrclone.IdentityDeliveryVault             = (*identityDeliveryHTTPVault)(nil)
	_ ashrclone.IdentityDeliverySMTPAdapter       = (*identityDeliveryHTTPAdapter)(nil)
	_ ashrclone.IdentityDeliverySMSAdapter        = (*identityDeliveryHTTPAdapter)(nil)
	_ ashrclone.IdentityDeliveryAcceptanceAdapter = (*identityDeliveryHTTPAdapter)(nil)
)
