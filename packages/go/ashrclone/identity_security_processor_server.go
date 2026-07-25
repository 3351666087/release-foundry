package ashrclone

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net/http"
	"strings"
	"time"
)

const maxIdentitySecurityProcessorRequestBytes = 32 * 1024

type IdentitySecurityProcessorReadiness interface {
	Ready(context.Context) error
}

type IdentitySecurityProcessorHandlerOptions struct {
	Processor        IdentitySecuritySecretProcessor
	Readiness        IdentitySecurityProcessorReadiness
	ReadinessTimeout time.Duration
}

type identitySecurityProcessorHandler struct {
	processor        IdentitySecuritySecretProcessor
	readiness        IdentitySecurityProcessorReadiness
	readinessTimeout time.Duration
}

func NewIdentitySecurityProcessorHandler(
	options IdentitySecurityProcessorHandlerOptions,
) (http.Handler, error) {
	if options.Processor == nil || options.Readiness == nil {
		return nil, errors.New("identity security processor handler dependencies are required")
	}
	if options.ReadinessTimeout < time.Millisecond ||
		options.ReadinessTimeout > 30*time.Second {
		return nil, errors.New("identity security processor readiness timeout must be between 1ms and 30s")
	}
	handler := &identitySecurityProcessorHandler{
		processor:        options.Processor,
		readiness:        options.Readiness,
		readinessTimeout: options.ReadinessTimeout,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", handler.health)
	mux.HandleFunc("/ready", handler.ready)
	mux.HandleFunc("/v1/identity/security/process", handler.process)
	mux.HandleFunc("/v1/identity/security/confirm", handler.confirm)
	mux.HandleFunc(
		"/v1/identity/security/handoff/consume",
		handler.consumeHandoff,
	)
	mux.HandleFunc("/v1/identity/security/cleanup", handler.cleanup)
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		setIdentitySecurityProcessorNoStoreHeaders(writer.Header())
		mux.ServeHTTP(writer, request)
	}), nil
}

func (handler *identitySecurityProcessorHandler) health(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if request.Method != http.MethodGet {
		writeIdentitySecurityProcessorMethodNotAllowed(writer, http.MethodGet)
		return
	}
	writeIdentitySecurityProcessorJSON(writer, http.StatusOK, struct {
		SchemaVersion string `json:"schema_version"`
		Status        string `json:"status"`
	}{
		SchemaVersion: IdentitySecurityProcessorSchemaVersion,
		Status:        "ok",
	})
}

func (handler *identitySecurityProcessorHandler) ready(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if request.Method != http.MethodGet {
		writeIdentitySecurityProcessorMethodNotAllowed(writer, http.MethodGet)
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), handler.readinessTimeout)
	defer cancel()
	if err := handler.readiness.Ready(ctx); err != nil {
		writeIdentitySecurityProcessorError(
			writer,
			http.StatusServiceUnavailable,
			"unavailable",
		)
		return
	}
	writeIdentitySecurityProcessorJSON(writer, http.StatusOK, struct {
		SchemaVersion string `json:"schema_version"`
		Status        string `json:"status"`
	}{
		SchemaVersion: IdentitySecurityProcessorSchemaVersion,
		Status:        "ready",
	})
}

func (handler *identitySecurityProcessorHandler) process(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if request.Method != http.MethodPost {
		writeIdentitySecurityProcessorMethodNotAllowed(writer, http.MethodPost)
		return
	}
	var payload struct {
		SchemaVersion  string `json:"schema_version"`
		AccountID      string `json:"account_id"`
		Operation      string `json:"operation"`
		IdempotencyKey string `json:"idempotency_key"`
		Password       string `json:"password,omitempty"`
	}
	if !decodeIdentitySecurityProcessorRequest(writer, request, &payload) {
		return
	}
	if payload.SchemaVersion != IdentitySecurityProcessorSchemaVersion {
		writeIdentitySecurityProcessorError(
			writer,
			http.StatusBadRequest,
			"invalid_request",
		)
		return
	}
	result, err := handler.processor.ProcessIdentitySecuritySecret(
		request.Context(),
		IdentitySecuritySecretProcessRequest{
			AccountID:      payload.AccountID,
			Operation:      payload.Operation,
			IdempotencyKey: payload.IdempotencyKey,
			Password:       payload.Password,
		},
	)
	payload.Password = ""
	if err != nil {
		writeIdentitySecurityProcessorOperationError(writer, err)
		return
	}
	writeIdentitySecurityProcessorJSON(writer, http.StatusCreated, struct {
		SchemaVersion           string `json:"schema_version"`
		SecretRef               string `json:"secret_ref"`
		SecretDigest            string `json:"secret_digest"`
		KeyVersion              string `json:"key_version"`
		ConfirmationChallengeID string `json:"confirmation_challenge_id,omitempty"`
		HandoffID               string `json:"handoff_id,omitempty"`
		CleanupToken            string `json:"cleanup_token"`
	}{
		SchemaVersion:           IdentitySecurityProcessorSchemaVersion,
		SecretRef:               result.SecretRef,
		SecretDigest:            result.SecretDigest,
		KeyVersion:              result.KeyVersion,
		ConfirmationChallengeID: result.ConfirmationChallengeID,
		HandoffID:               result.HandoffID,
		CleanupToken:            result.CleanupToken,
	})
}

func (handler *identitySecurityProcessorHandler) confirm(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if request.Method != http.MethodPost {
		writeIdentitySecurityProcessorMethodNotAllowed(writer, http.MethodPost)
		return
	}
	var payload struct {
		SchemaVersion  string `json:"schema_version"`
		AccountID      string `json:"account_id"`
		ChallengeID    string `json:"challenge_id"`
		Code           string `json:"code"`
		IdempotencyKey string `json:"idempotency_key"`
	}
	if !decodeIdentitySecurityProcessorRequest(writer, request, &payload) {
		return
	}
	if payload.SchemaVersion != IdentitySecurityProcessorSchemaVersion {
		writeIdentitySecurityProcessorError(
			writer,
			http.StatusBadRequest,
			"invalid_request",
		)
		return
	}
	result, err := handler.processor.ConfirmIdentitySecuritySecret(
		request.Context(),
		IdentitySecuritySecretConfirmRequest{
			AccountID:      payload.AccountID,
			ChallengeID:    payload.ChallengeID,
			Code:           payload.Code,
			IdempotencyKey: payload.IdempotencyKey,
		},
	)
	payload.Code = ""
	if err != nil {
		writeIdentitySecurityProcessorOperationError(writer, err)
		return
	}
	writeIdentitySecurityProcessorJSON(writer, http.StatusOK, struct {
		SchemaVersion       string `json:"schema_version"`
		RecoveryBatchDigest string `json:"recovery_batch_digest"`
		RecoveryCodeCount   int    `json:"recovery_code_count"`
		KeyVersion          string `json:"key_version"`
		HandoffID           string `json:"handoff_id"`
		CleanupToken        string `json:"cleanup_token"`
	}{
		SchemaVersion:       IdentitySecurityProcessorSchemaVersion,
		RecoveryBatchDigest: result.RecoveryBatchDigest,
		RecoveryCodeCount:   result.RecoveryCodeCount,
		KeyVersion:          result.KeyVersion,
		HandoffID:           result.HandoffID,
		CleanupToken:        result.CleanupToken,
	})
}

func (handler *identitySecurityProcessorHandler) consumeHandoff(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if request.Method != http.MethodPost {
		writeIdentitySecurityProcessorMethodNotAllowed(writer, http.MethodPost)
		return
	}
	var payload struct {
		SchemaVersion  string `json:"schema_version"`
		AccountID      string `json:"account_id"`
		Operation      string `json:"operation"`
		IdempotencyKey string `json:"idempotency_key"`
		HandoffID      string `json:"handoff_id"`
	}
	if !decodeIdentitySecurityProcessorRequest(writer, request, &payload) {
		return
	}
	if payload.SchemaVersion != IdentitySecurityProcessorSchemaVersion {
		writeIdentitySecurityProcessorError(
			writer,
			http.StatusBadRequest,
			"invalid_request",
		)
		return
	}
	result, err := handler.processor.ConsumeIdentitySecuritySecretHandoff(
		request.Context(),
		IdentitySecuritySecretHandoffRequest{
			AccountID:      payload.AccountID,
			Operation:      payload.Operation,
			IdempotencyKey: payload.IdempotencyKey,
			HandoffID:      payload.HandoffID,
		},
	)
	if err != nil {
		writeIdentitySecurityProcessorOperationError(writer, err)
		return
	}
	writeIdentitySecurityProcessorJSON(writer, http.StatusOK, struct {
		SchemaVersion   string   `json:"schema_version"`
		ProvisioningURI string   `json:"provisioning_uri,omitempty"`
		RecoveryCodes   []string `json:"recovery_codes,omitempty"`
	}{
		SchemaVersion:   IdentitySecurityProcessorSchemaVersion,
		ProvisioningURI: result.ProvisioningURI,
		RecoveryCodes:   result.RecoveryCodes,
	})
	clearIdentitySecuritySecretHandoff(&result)
}

func (handler *identitySecurityProcessorHandler) cleanup(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if request.Method != http.MethodPost {
		writeIdentitySecurityProcessorMethodNotAllowed(writer, http.MethodPost)
		return
	}
	var payload struct {
		SchemaVersion  string `json:"schema_version"`
		AccountID      string `json:"account_id"`
		Operation      string `json:"operation"`
		IdempotencyKey string `json:"idempotency_key"`
		CleanupToken   string `json:"cleanup_token"`
	}
	if !decodeIdentitySecurityProcessorRequest(writer, request, &payload) {
		return
	}
	if payload.SchemaVersion != IdentitySecurityProcessorSchemaVersion {
		writeIdentitySecurityProcessorError(
			writer,
			http.StatusBadRequest,
			"invalid_request",
		)
		return
	}
	err := handler.processor.CleanupIdentitySecuritySecret(
		request.Context(),
		IdentitySecuritySecretCleanupRequest{
			AccountID:      payload.AccountID,
			Operation:      payload.Operation,
			IdempotencyKey: payload.IdempotencyKey,
			CleanupToken:   payload.CleanupToken,
		},
	)
	if err != nil {
		writeIdentitySecurityProcessorOperationError(writer, err)
		return
	}
	writer.WriteHeader(http.StatusNoContent)
}

func decodeIdentitySecurityProcessorRequest(
	writer http.ResponseWriter,
	request *http.Request,
	target any,
) bool {
	mediaType, _, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		writeIdentitySecurityProcessorError(
			writer,
			http.StatusBadRequest,
			"invalid_request",
		)
		return false
	}
	body, err := io.ReadAll(
		http.MaxBytesReader(
			writer,
			request.Body,
			maxIdentitySecurityProcessorRequestBytes,
		),
	)
	if err != nil || len(body) == 0 {
		clear(body)
		writeIdentitySecurityProcessorError(
			writer,
			http.StatusBadRequest,
			"invalid_request",
		)
		return false
	}
	defer clear(body)
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeIdentitySecurityProcessorError(
			writer,
			http.StatusBadRequest,
			"invalid_request",
		)
		return false
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		writeIdentitySecurityProcessorError(
			writer,
			http.StatusBadRequest,
			"invalid_request",
		)
		return false
	}
	return true
}

func writeIdentitySecurityProcessorOperationError(
	writer http.ResponseWriter,
	err error,
) {
	if errors.Is(err, ErrIdentitySecurityProcessorRejected) {
		writeIdentitySecurityProcessorError(writer, http.StatusForbidden, "rejected")
		return
	}
	writeIdentitySecurityProcessorError(
		writer,
		http.StatusServiceUnavailable,
		"unavailable",
	)
}

func writeIdentitySecurityProcessorMethodNotAllowed(
	writer http.ResponseWriter,
	allowedMethod string,
) {
	writer.Header().Set("Allow", allowedMethod)
	writeIdentitySecurityProcessorError(
		writer,
		http.StatusMethodNotAllowed,
		"method_not_allowed",
	)
}

func writeIdentitySecurityProcessorError(
	writer http.ResponseWriter,
	status int,
	code string,
) {
	writeIdentitySecurityProcessorJSON(writer, status, struct {
		SchemaVersion string `json:"schema_version"`
		Code          string `json:"code"`
	}{
		SchemaVersion: IdentitySecurityProcessorSchemaVersion,
		Code:          strings.TrimSpace(code),
	})
}

func writeIdentitySecurityProcessorJSON(
	writer http.ResponseWriter,
	status int,
	payload any,
) {
	writer.Header().Set("Content-Type", "application/json")
	writer.Header().Set("X-Content-Type-Options", "nosniff")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func setIdentitySecurityProcessorNoStoreHeaders(header http.Header) {
	header.Set("Cache-Control", "no-store")
	header.Set("Pragma", "no-cache")
	header.Set("Referrer-Policy", "no-referrer")
}

var _ IdentitySecurityProcessorReadiness = (*VaultIdentitySecuritySecretProcessor)(
	nil,
)
