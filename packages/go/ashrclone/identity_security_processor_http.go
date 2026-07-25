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

const IdentitySecurityProcessorSchemaVersion = "ashr.identity_security_processor.v1"

const maxIdentitySecurityProcessorResponseBytes = 128 * 1024

const (
	identitySecurityProcessorProcessPath  = "/v1/identity/security/process"
	identitySecurityProcessorConfirmPath  = "/v1/identity/security/confirm"
	identitySecurityProcessorPreparePath  = "/v1/identity/security/mutations/prepare"
	identitySecurityProcessorFinalizePath = "/v1/identity/security/mutations/finalize"
	identitySecurityProcessorHandoffPath  = "/v1/identity/security/handoff/consume"
	identitySecurityProcessorCleanupPath  = "/v1/identity/security/cleanup"
	identitySecurityProcessorReadyPath    = "/ready"
)

type HTTPIdentitySecuritySecretProcessorOptions struct {
	ProcessEndpoint        string
	ConfirmEndpoint        string
	PrepareEndpoint        string
	FinalizeEndpoint       string
	HandoffConsumeEndpoint string
	CleanupEndpoint        string
	Client                 *http.Client
	Timeout                time.Duration
}

// HTTPIdentitySecuritySecretProcessor sends raw secret material only to a
// caller-authenticated HTTPS processor. Redirects and non-JSON responses are
// refused, and upstream bodies are never included in returned errors.
type HTTPIdentitySecuritySecretProcessor struct {
	processEndpoint        string
	confirmEndpoint        string
	prepareEndpoint        string
	finalizeEndpoint       string
	handoffConsumeEndpoint string
	cleanupEndpoint        string
	readinessEndpoint      string
	client                 *http.Client
	timeout                time.Duration
}

func NewHTTPIdentitySecuritySecretProcessor(
	options HTTPIdentitySecuritySecretProcessorOptions,
) (*HTTPIdentitySecuritySecretProcessor, error) {
	if options.Client == nil {
		return nil, errors.New("identity security processor authenticated client is required")
	}
	endpoints := []struct {
		value        *string
		expectedPath string
	}{
		{&options.ProcessEndpoint, identitySecurityProcessorProcessPath},
		{&options.ConfirmEndpoint, identitySecurityProcessorConfirmPath},
		{&options.PrepareEndpoint, identitySecurityProcessorPreparePath},
		{&options.FinalizeEndpoint, identitySecurityProcessorFinalizePath},
		{&options.HandoffConsumeEndpoint, identitySecurityProcessorHandoffPath},
		{&options.CleanupEndpoint, identitySecurityProcessorCleanupPath},
	}
	var processorOrigin string
	for _, endpoint := range endpoints {
		validated, origin, err := strictIdentitySecurityProcessorEndpoint(
			*endpoint.value,
			endpoint.expectedPath,
		)
		if err != nil {
			return nil, err
		}
		if processorOrigin == "" {
			processorOrigin = origin
		} else if processorOrigin != origin {
			return nil, errors.New(
				"identity security processor endpoints must use one HTTPS origin",
			)
		}
		*endpoint.value = validated
	}
	if options.Timeout < time.Millisecond || options.Timeout > 30*time.Second {
		return nil, errors.New("identity security processor timeout must be between 1ms and 30s")
	}
	client := *options.Client
	client.CheckRedirect = func(*http.Request, []*http.Request) error {
		return errors.New("identity security processor redirect refused")
	}
	return &HTTPIdentitySecuritySecretProcessor{
		processEndpoint:        options.ProcessEndpoint,
		confirmEndpoint:        options.ConfirmEndpoint,
		prepareEndpoint:        options.PrepareEndpoint,
		finalizeEndpoint:       options.FinalizeEndpoint,
		handoffConsumeEndpoint: options.HandoffConsumeEndpoint,
		cleanupEndpoint:        options.CleanupEndpoint,
		readinessEndpoint:      processorOrigin + identitySecurityProcessorReadyPath,
		client:                 &client,
		timeout:                options.Timeout,
	}, nil
}

func (processor *HTTPIdentitySecuritySecretProcessor) Ready(
	ctx context.Context,
) error {
	if processor == nil || processor.client == nil || ctx == nil ||
		processor.readinessEndpoint == "" {
		return ErrIdentitySecurityProcessorUnavailable
	}
	callCtx, cancel := context.WithTimeout(ctx, processor.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		callCtx,
		http.MethodGet,
		processor.readinessEndpoint,
		nil,
	)
	if err != nil {
		return ErrIdentitySecurityProcessorUnavailable
	}
	request.Header.Set("Accept", "application/json")
	response, err := processor.client.Do(request)
	if err != nil {
		return safeIdentitySecurityProcessorError(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(
			io.Discard,
			io.LimitReader(response.Body, maxIdentitySecurityProcessorResponseBytes),
		)
		return ErrIdentitySecurityProcessorUnavailable
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return ErrIdentitySecurityProcessorUnavailable
	}
	body, err := io.ReadAll(
		io.LimitReader(response.Body, maxIdentitySecurityProcessorResponseBytes+1),
	)
	if err != nil || len(body) > maxIdentitySecurityProcessorResponseBytes {
		clear(body)
		return ErrIdentitySecurityProcessorUnavailable
	}
	defer clear(body)
	var ready struct {
		SchemaVersion string `json:"schema_version"`
		Status        string `json:"status"`
	}
	if decodeStrictIdentitySecurityProcessorJSON(body, &ready) != nil ||
		ready.SchemaVersion != IdentitySecurityProcessorSchemaVersion ||
		ready.Status != "ready" {
		return ErrIdentitySecurityProcessorUnavailable
	}
	return nil
}

func (processor *HTTPIdentitySecuritySecretProcessor) ProcessIdentitySecuritySecret(
	ctx context.Context,
	request IdentitySecuritySecretProcessRequest,
) (IdentitySecuritySecretProcessResult, error) {
	if processor == nil || processor.client == nil || ctx == nil ||
		!validIdentitySecuritySecretProcessRequest(request) {
		return IdentitySecuritySecretProcessResult{}, ErrIdentitySecurityProcessorRejected
	}
	responseBody, err := processor.postJSON(ctx, processor.processEndpoint, struct {
		SchemaVersion  string `json:"schema_version"`
		AccountID      string `json:"account_id"`
		Operation      string `json:"operation"`
		IdempotencyKey string `json:"idempotency_key"`
		Password       string `json:"password,omitempty"`
	}{
		SchemaVersion:  IdentitySecurityProcessorSchemaVersion,
		AccountID:      strings.TrimSpace(request.AccountID),
		Operation:      strings.TrimSpace(request.Operation),
		IdempotencyKey: strings.TrimSpace(request.IdempotencyKey),
		Password:       request.Password,
	}, http.StatusOK, http.StatusCreated)
	if err != nil {
		return IdentitySecuritySecretProcessResult{}, err
	}
	defer clear(responseBody)
	var response struct {
		SchemaVersion           string `json:"schema_version"`
		SecretRef               string `json:"secret_ref"`
		SecretDigest            string `json:"secret_digest"`
		KeyVersion              string `json:"key_version"`
		ConfirmationChallengeID string `json:"confirmation_challenge_id,omitempty"`
		HandoffID               string `json:"handoff_id,omitempty"`
		CleanupToken            string `json:"cleanup_token"`
	}
	if err := decodeStrictIdentitySecurityProcessorJSON(
		responseBody,
		&response,
	); err != nil || response.SchemaVersion != IdentitySecurityProcessorSchemaVersion {
		return IdentitySecuritySecretProcessResult{}, ErrIdentitySecurityProcessorUnavailable
	}
	result := IdentitySecuritySecretProcessResult{
		SecretRef:               response.SecretRef,
		SecretDigest:            response.SecretDigest,
		KeyVersion:              response.KeyVersion,
		ConfirmationChallengeID: response.ConfirmationChallengeID,
		HandoffID:               response.HandoffID,
		CleanupToken:            response.CleanupToken,
	}
	if !validIdentitySecuritySecretProcessResult(request.Operation, result) {
		return IdentitySecuritySecretProcessResult{}, ErrIdentitySecurityProcessorUnavailable
	}
	return result, nil
}

func (processor *HTTPIdentitySecuritySecretProcessor) ConfirmIdentitySecuritySecret(
	ctx context.Context,
	request IdentitySecuritySecretConfirmRequest,
) (IdentitySecuritySecretConfirmResult, error) {
	if processor == nil || processor.client == nil || ctx == nil ||
		!validIdentitySecuritySecretConfirmRequest(request) {
		return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorRejected
	}
	responseBody, err := processor.postJSON(ctx, processor.confirmEndpoint, struct {
		SchemaVersion  string `json:"schema_version"`
		AccountID      string `json:"account_id"`
		ChallengeID    string `json:"challenge_id"`
		Code           string `json:"code"`
		IdempotencyKey string `json:"idempotency_key"`
	}{
		SchemaVersion:  IdentitySecurityProcessorSchemaVersion,
		AccountID:      strings.TrimSpace(request.AccountID),
		ChallengeID:    strings.TrimSpace(request.ChallengeID),
		Code:           strings.TrimSpace(request.Code),
		IdempotencyKey: strings.TrimSpace(request.IdempotencyKey),
	}, http.StatusOK)
	if err != nil {
		return IdentitySecuritySecretConfirmResult{}, err
	}
	defer clear(responseBody)
	var response struct {
		SchemaVersion       string `json:"schema_version"`
		RecoveryBatchDigest string `json:"recovery_batch_digest"`
		RecoveryCodeCount   int    `json:"recovery_code_count"`
		KeyVersion          string `json:"key_version"`
		HandoffID           string `json:"handoff_id"`
		CleanupToken        string `json:"cleanup_token"`
	}
	if err := decodeStrictIdentitySecurityProcessorJSON(
		responseBody,
		&response,
	); err != nil || response.SchemaVersion != IdentitySecurityProcessorSchemaVersion {
		return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorUnavailable
	}
	result := IdentitySecuritySecretConfirmResult{
		RecoveryBatchDigest: response.RecoveryBatchDigest,
		RecoveryCodeCount:   response.RecoveryCodeCount,
		KeyVersion:          response.KeyVersion,
		HandoffID:           response.HandoffID,
		CleanupToken:        response.CleanupToken,
	}
	if !validIdentitySecuritySecretConfirmResult(result) {
		return IdentitySecuritySecretConfirmResult{}, ErrIdentitySecurityProcessorUnavailable
	}
	return result, nil
}

func (processor *HTTPIdentitySecuritySecretProcessor) PrepareIdentitySecuritySecretMutation(
	ctx context.Context,
	request IdentitySecuritySecretMutationPrepareRequest,
) (IdentitySecuritySecretMutationPrepareResult, error) {
	if processor == nil || processor.client == nil || ctx == nil ||
		!validIdentitySecuritySecretMutationPrepareRequest(request) {
		return IdentitySecuritySecretMutationPrepareResult{},
			ErrIdentitySecurityProcessorRejected
	}
	responseBody, err := processor.postJSON(
		ctx,
		processor.prepareEndpoint,
		struct {
			SchemaVersion               string `json:"schema_version"`
			AccountID                   string `json:"account_id"`
			Operation                   string `json:"operation"`
			IdempotencyKey              string `json:"idempotency_key"`
			SecretRef                   string `json:"secret_ref"`
			SecretDigest                string `json:"secret_digest"`
			ExpectedRecoveryBatchDigest string `json:"expected_recovery_batch_digest"`
			ExpectedRecoveryCodeCount   int    `json:"expected_recovery_code_count"`
			RecoveryCode                string `json:"recovery_code,omitempty"`
		}{
			SchemaVersion:  IdentitySecurityProcessorSchemaVersion,
			AccountID:      strings.TrimSpace(request.AccountID),
			Operation:      strings.TrimSpace(request.Operation),
			IdempotencyKey: strings.TrimSpace(request.IdempotencyKey),
			SecretRef:      strings.TrimSpace(request.SecretRef),
			SecretDigest:   strings.TrimSpace(request.SecretDigest),
			ExpectedRecoveryBatchDigest: strings.TrimSpace(
				request.ExpectedRecoveryBatchDigest,
			),
			ExpectedRecoveryCodeCount: request.ExpectedRecoveryCodeCount,
			RecoveryCode:              strings.TrimSpace(request.RecoveryCode),
		},
		http.StatusOK,
		http.StatusCreated,
	)
	if err != nil {
		return IdentitySecuritySecretMutationPrepareResult{}, err
	}
	defer clear(responseBody)
	var response struct {
		SchemaVersion               string `json:"schema_version"`
		SecretRef                   string `json:"secret_ref"`
		SecretDigest                string `json:"secret_digest"`
		ExpectedRecoveryBatchDigest string `json:"expected_recovery_batch_digest"`
		ExpectedRecoveryCodeCount   int    `json:"expected_recovery_code_count"`
		RecoveryBatchDigest         string `json:"recovery_batch_digest,omitempty"`
		RecoveryCodeCount           int    `json:"recovery_code_count"`
		KeyVersion                  string `json:"key_version"`
		HandoffID                   string `json:"handoff_id,omitempty"`
		FinalizeToken               string `json:"finalize_token"`
		CleanupToken                string `json:"cleanup_token"`
	}
	if err := decodeStrictIdentitySecurityProcessorJSON(
		responseBody,
		&response,
	); err != nil ||
		response.SchemaVersion != IdentitySecurityProcessorSchemaVersion {
		return IdentitySecuritySecretMutationPrepareResult{},
			ErrIdentitySecurityProcessorUnavailable
	}
	result := IdentitySecuritySecretMutationPrepareResult{
		SecretRef:                   response.SecretRef,
		SecretDigest:                response.SecretDigest,
		ExpectedRecoveryBatchDigest: response.ExpectedRecoveryBatchDigest,
		ExpectedRecoveryCodeCount:   response.ExpectedRecoveryCodeCount,
		RecoveryBatchDigest:         response.RecoveryBatchDigest,
		RecoveryCodeCount:           response.RecoveryCodeCount,
		KeyVersion:                  response.KeyVersion,
		HandoffID:                   response.HandoffID,
		FinalizeToken:               response.FinalizeToken,
		CleanupToken:                response.CleanupToken,
	}
	if !validIdentitySecuritySecretMutationPrepareResult(
		request.Operation,
		result,
	) {
		return IdentitySecuritySecretMutationPrepareResult{},
			ErrIdentitySecurityProcessorUnavailable
	}
	return result, nil
}

func (processor *HTTPIdentitySecuritySecretProcessor) FinalizeIdentitySecuritySecretMutation(
	ctx context.Context,
	request IdentitySecuritySecretMutationFinalizeRequest,
) error {
	if processor == nil || processor.client == nil || ctx == nil ||
		!validIdentitySecuritySecretMutationFinalizeRequest(request) {
		return ErrIdentitySecurityProcessorRejected
	}
	responseBody, err := processor.postJSON(
		context.WithoutCancel(ctx),
		processor.finalizeEndpoint,
		struct {
			SchemaVersion  string `json:"schema_version"`
			AccountID      string `json:"account_id"`
			Operation      string `json:"operation"`
			IdempotencyKey string `json:"idempotency_key"`
			FinalizeToken  string `json:"finalize_token"`
		}{
			SchemaVersion:  IdentitySecurityProcessorSchemaVersion,
			AccountID:      strings.TrimSpace(request.AccountID),
			Operation:      strings.TrimSpace(request.Operation),
			IdempotencyKey: strings.TrimSpace(request.IdempotencyKey),
			FinalizeToken:  strings.TrimSpace(request.FinalizeToken),
		},
		http.StatusOK,
		http.StatusNoContent,
	)
	clear(responseBody)
	return err
}

func (processor *HTTPIdentitySecuritySecretProcessor) ConsumeIdentitySecuritySecretHandoff(
	ctx context.Context,
	request IdentitySecuritySecretHandoffRequest,
) (IdentitySecuritySecretHandoff, error) {
	if processor == nil || processor.client == nil || ctx == nil ||
		!validIdentitySecuritySecretHandoffRequest(request) {
		return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorRejected
	}
	responseBody, err := processor.postJSON(
		ctx,
		processor.handoffConsumeEndpoint,
		struct {
			SchemaVersion  string `json:"schema_version"`
			AccountID      string `json:"account_id"`
			Operation      string `json:"operation"`
			IdempotencyKey string `json:"idempotency_key"`
			HandoffID      string `json:"handoff_id"`
		}{
			SchemaVersion:  IdentitySecurityProcessorSchemaVersion,
			AccountID:      strings.TrimSpace(request.AccountID),
			Operation:      strings.TrimSpace(request.Operation),
			IdempotencyKey: strings.TrimSpace(request.IdempotencyKey),
			HandoffID:      strings.TrimSpace(request.HandoffID),
		},
		http.StatusOK,
	)
	if err != nil {
		return IdentitySecuritySecretHandoff{}, err
	}
	defer clear(responseBody)
	var response struct {
		SchemaVersion   string   `json:"schema_version"`
		ProvisioningURI string   `json:"provisioning_uri,omitempty"`
		RecoveryCodes   []string `json:"recovery_codes,omitempty"`
	}
	if err := decodeStrictIdentitySecurityProcessorJSON(
		responseBody,
		&response,
	); err != nil || response.SchemaVersion != IdentitySecurityProcessorSchemaVersion {
		return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorUnavailable
	}
	handoff := IdentitySecuritySecretHandoff{
		ProvisioningURI: response.ProvisioningURI,
		RecoveryCodes:   append([]string(nil), response.RecoveryCodes...),
	}
	if !validIdentitySecuritySecretHandoff(request.Operation, handoff) {
		return IdentitySecuritySecretHandoff{}, ErrIdentitySecurityProcessorUnavailable
	}
	return handoff, nil
}

func (processor *HTTPIdentitySecuritySecretProcessor) CleanupIdentitySecuritySecret(
	ctx context.Context,
	request IdentitySecuritySecretCleanupRequest,
) error {
	if processor == nil || processor.client == nil || ctx == nil ||
		!validIdentitySecuritySecretCleanupRequest(request) {
		return ErrIdentitySecurityProcessorRejected
	}
	responseBody, err := processor.postJSON(
		context.WithoutCancel(ctx),
		processor.cleanupEndpoint,
		struct {
			SchemaVersion  string `json:"schema_version"`
			AccountID      string `json:"account_id"`
			Operation      string `json:"operation"`
			IdempotencyKey string `json:"idempotency_key"`
			CleanupToken   string `json:"cleanup_token"`
		}{
			SchemaVersion:  IdentitySecurityProcessorSchemaVersion,
			AccountID:      strings.TrimSpace(request.AccountID),
			Operation:      strings.TrimSpace(request.Operation),
			IdempotencyKey: strings.TrimSpace(request.IdempotencyKey),
			CleanupToken:   strings.TrimSpace(request.CleanupToken),
		},
		http.StatusOK,
		http.StatusNoContent,
		http.StatusNotFound,
	)
	clear(responseBody)
	return err
}

func (processor *HTTPIdentitySecuritySecretProcessor) postJSON(
	ctx context.Context,
	endpoint string,
	payload any,
	acceptedStatuses ...int,
) ([]byte, error) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, ErrIdentitySecurityProcessorRejected
	}
	defer clear(encoded)
	callCtx, cancel := context.WithTimeout(ctx, processor.timeout)
	defer cancel()
	httpRequest, err := http.NewRequestWithContext(
		callCtx,
		http.MethodPost,
		endpoint,
		bytes.NewReader(encoded),
	)
	if err != nil {
		return nil, ErrIdentitySecurityProcessorRejected
	}
	httpRequest.Header.Set("Content-Type", "application/json")
	httpRequest.Header.Set("Accept", "application/json")
	response, err := processor.client.Do(httpRequest)
	if err != nil {
		return nil, safeIdentitySecurityProcessorError(err)
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
		_, _ = io.Copy(
			io.Discard,
			io.LimitReader(response.Body, maxIdentitySecurityProcessorResponseBytes),
		)
		if response.StatusCode >= 400 && response.StatusCode < 500 {
			return nil, ErrIdentitySecurityProcessorRejected
		}
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	if response.StatusCode == http.StatusNoContent ||
		response.StatusCode == http.StatusNotFound {
		_, _ = io.Copy(
			io.Discard,
			io.LimitReader(response.Body, maxIdentitySecurityProcessorResponseBytes),
		)
		return nil, nil
	}
	mediaType, _, err := mime.ParseMediaType(response.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	body, err := io.ReadAll(
		io.LimitReader(response.Body, maxIdentitySecurityProcessorResponseBytes+1),
	)
	if err != nil || len(body) > maxIdentitySecurityProcessorResponseBytes {
		clear(body)
		return nil, ErrIdentitySecurityProcessorUnavailable
	}
	return body, nil
}

func strictIdentitySecurityProcessorEndpoint(
	raw string,
	expectedPath string,
) (string, string, error) {
	if raw == "" || raw != strings.TrimSpace(raw) ||
		strings.ContainsAny(raw, "\x00\r\n\t") {
		return "", "", errors.New(
			"identity security processor endpoint must be an absolute HTTPS URL",
		)
	}
	parsed, err := url.ParseRequestURI(raw)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" ||
		parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" ||
		parsed.Opaque != "" || parsed.RawPath != "" || parsed.ForceQuery ||
		parsed.Path != expectedPath {
		return "", "", errors.New(
			"identity security processor endpoint must use its exact absolute HTTPS path",
		)
	}
	origin := (&url.URL{Scheme: parsed.Scheme, Host: parsed.Host}).String()
	return parsed.String(), origin, nil
}

func decodeStrictIdentitySecurityProcessorJSON(body []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return fmt.Errorf("identity security processor response has trailing content")
	}
	return nil
}

func safeIdentitySecurityProcessorError(err error) error {
	switch {
	case errors.Is(err, context.DeadlineExceeded):
		return fmt.Errorf(
			"identity security processor request timed out: %w",
			context.DeadlineExceeded,
		)
	case errors.Is(err, context.Canceled):
		return fmt.Errorf(
			"identity security processor request canceled: %w",
			context.Canceled,
		)
	default:
		return ErrIdentitySecurityProcessorUnavailable
	}
}

var _ IdentitySecuritySecretProcessor = (*HTTPIdentitySecuritySecretProcessor)(nil)
var _ IdentitySecurityProcessorReadiness = (*HTTPIdentitySecuritySecretProcessor)(nil)
