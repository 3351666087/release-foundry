package ashrclone

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

const identitySecurityProcessorTestAccountID = "33333333-3333-4333-8333-333333333333"

func identitySecurityProcessorTestOptions(
	server *httptest.Server,
	timeout time.Duration,
) HTTPIdentitySecuritySecretProcessorOptions {
	return HTTPIdentitySecuritySecretProcessorOptions{
		ProcessEndpoint:        server.URL + identitySecurityProcessorProcessPath,
		ConfirmEndpoint:        server.URL + identitySecurityProcessorConfirmPath,
		PrepareEndpoint:        server.URL + identitySecurityProcessorPreparePath,
		FinalizeEndpoint:       server.URL + identitySecurityProcessorFinalizePath,
		HandoffConsumeEndpoint: server.URL + identitySecurityProcessorHandoffPath,
		CleanupEndpoint:        server.URL + identitySecurityProcessorCleanupPath,
		Client:                 server.Client(),
		Timeout:                timeout,
	}
}

func writeIdentitySecurityProcessorTestJSON(
	writer http.ResponseWriter,
	status int,
	payload any,
) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(payload)
}

func TestHTTPIdentitySecuritySecretProcessorValidatesEndpointsAndClient(t *testing.T) {
	server := httptest.NewTLSServer(http.NotFoundHandler())
	defer server.Close()

	options := identitySecurityProcessorTestOptions(server, time.Second)
	if _, err := NewHTTPIdentitySecuritySecretProcessor(options); err != nil {
		t.Fatalf("construct HTTPS processor: %v", err)
	}

	for name, mutate := range map[string]func(*HTTPIdentitySecuritySecretProcessorOptions){
		"missing client": func(options *HTTPIdentitySecuritySecretProcessorOptions) {
			options.Client = nil
		},
		"plain HTTP": func(options *HTTPIdentitySecuritySecretProcessorOptions) {
			options.ProcessEndpoint = "http://processor.example.test" +
				identitySecurityProcessorProcessPath
		},
		"query": func(options *HTTPIdentitySecuritySecretProcessorOptions) {
			options.ConfirmEndpoint += "?unsafe=true"
		},
		"userinfo": func(options *HTTPIdentitySecuritySecretProcessorOptions) {
			options.CleanupEndpoint = "https://user@processor.example.test" +
				identitySecurityProcessorCleanupPath
		},
		"wrong path": func(options *HTTPIdentitySecuritySecretProcessorOptions) {
			options.ProcessEndpoint = server.URL + "/v1/process"
		},
		"mixed origin": func(options *HTTPIdentitySecuritySecretProcessorOptions) {
			options.ConfirmEndpoint = "https://other.example.test" +
				identitySecurityProcessorConfirmPath
		},
		"invalid timeout": func(options *HTTPIdentitySecuritySecretProcessorOptions) {
			options.Timeout = 31 * time.Second
		},
	} {
		t.Run(name, func(t *testing.T) {
			invalid := options
			mutate(&invalid)
			if _, err := NewHTTPIdentitySecuritySecretProcessor(invalid); err == nil {
				t.Fatal("unsafe processor configuration was accepted")
			}
		})
	}
}

func TestHTTPIdentitySecuritySecretProcessorRoundTripIsStrictAndSecretSafe(t *testing.T) {
	reference := "isr_" + strings.Repeat("A", 24)
	challenge := "isc_" + strings.Repeat("B", 24)
	handoff := "ish_" + strings.Repeat("C", 24)
	cleanup := "isx_" + strings.Repeat("D", 24)
	finalize := "isf_" + strings.Repeat("E", 24)
	digest := strings.Repeat("a", 64)
	recoveryDigest := strings.Repeat("b", 64)
	nextRecoveryDigest := strings.Repeat("c", 64)
	recoveryCodes := []string{
		"A1BC-DEFG", "B2CD-EFGH", "C3DE-FGHJ",
		"D4EF-GHJK", "E5FG-HJKL", "F6GH-JKLM",
	}
	var paths []string
	server := httptest.NewTLSServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			paths = append(paths, request.URL.Path)
			if request.Method != http.MethodPost ||
				request.Header.Get("Content-Type") != "application/json" ||
				request.Header.Get("Accept") != "application/json" {
				t.Errorf("unexpected processor request envelope")
			}
			var body map[string]any
			if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
				t.Errorf("decode processor request: %v", err)
				return
			}
			if body["schema_version"] != IdentitySecurityProcessorSchemaVersion ||
				body["account_id"] != identitySecurityProcessorTestAccountID {
				t.Errorf("processor request lost schema/account binding")
			}
			switch request.URL.Path {
			case identitySecurityProcessorProcessPath:
				if body["operation"] == "mfa_enroll" {
					writeIdentitySecurityProcessorTestJSON(writer, http.StatusCreated, map[string]any{
						"schema_version":            IdentitySecurityProcessorSchemaVersion,
						"secret_ref":                reference,
						"secret_digest":             digest,
						"key_version":               "key-v1",
						"confirmation_challenge_id": challenge,
						"handoff_id":                handoff,
						"cleanup_token":             cleanup,
					})
					return
				}
				writeIdentitySecurityProcessorTestJSON(writer, http.StatusOK, map[string]any{
					"schema_version": IdentitySecurityProcessorSchemaVersion,
					"secret_ref":     reference,
					"secret_digest":  digest,
					"key_version":    "key-v1",
					"cleanup_token":  cleanup,
				})
			case identitySecurityProcessorConfirmPath:
				writeIdentitySecurityProcessorTestJSON(writer, http.StatusOK, map[string]any{
					"schema_version":        IdentitySecurityProcessorSchemaVersion,
					"recovery_batch_digest": recoveryDigest,
					"recovery_code_count":   len(recoveryCodes),
					"key_version":           "key-v1",
					"handoff_id":            handoff,
					"cleanup_token":         cleanup,
				})
			case identitySecurityProcessorPreparePath:
				if body["operation"] != "mfa_recovery_consume" ||
					body["recovery_code"] != recoveryCodes[0] ||
					body["expected_recovery_batch_digest"] != recoveryDigest ||
					body["expected_recovery_code_count"] != float64(len(recoveryCodes)) {
					t.Errorf("mutation prepare lost trusted recovery context")
				}
				writeIdentitySecurityProcessorTestJSON(writer, http.StatusCreated, map[string]any{
					"schema_version":                 IdentitySecurityProcessorSchemaVersion,
					"secret_ref":                     reference,
					"secret_digest":                  digest,
					"expected_recovery_batch_digest": recoveryDigest,
					"expected_recovery_code_count":   len(recoveryCodes),
					"recovery_batch_digest":          nextRecoveryDigest,
					"recovery_code_count":            len(recoveryCodes) - 1,
					"key_version":                    "key-v1",
					"finalize_token":                 finalize,
					"cleanup_token":                  cleanup,
				})
			case identitySecurityProcessorFinalizePath:
				if body["operation"] != "mfa_recovery_consume" ||
					body["finalize_token"] != finalize {
					t.Errorf("mutation finalize lost its opaque binding")
				}
				writer.WriteHeader(http.StatusNoContent)
			case identitySecurityProcessorHandoffPath:
				if body["operation"] == "mfa_confirm" {
					writeIdentitySecurityProcessorTestJSON(writer, http.StatusOK, map[string]any{
						"schema_version": IdentitySecurityProcessorSchemaVersion,
						"recovery_codes": recoveryCodes,
					})
					return
				}
				writeIdentitySecurityProcessorTestJSON(writer, http.StatusOK, map[string]any{
					"schema_version":   IdentitySecurityProcessorSchemaVersion,
					"provisioning_uri": "otpauth://totp/Ashr:test?secret=ABCDEF234567",
				})
			case identitySecurityProcessorCleanupPath:
				writer.WriteHeader(http.StatusNoContent)
			default:
				http.NotFound(writer, request)
			}
		},
	))
	defer server.Close()

	processor, err := NewHTTPIdentitySecuritySecretProcessor(
		identitySecurityProcessorTestOptions(server, time.Second),
	)
	if err != nil {
		t.Fatalf("construct processor: %v", err)
	}
	passwordResult, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretProcessRequest{
			AccountID:      identitySecurityProcessorTestAccountID,
			Operation:      "password_enroll",
			IdempotencyKey: "password-enroll-1",
			Password:       "TwelveChars1!",
		},
	)
	if err != nil || passwordResult.SecretRef != reference {
		t.Fatalf("process password: result=%#v err=%v", passwordResult, err)
	}
	enrollResult, err := processor.ProcessIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretProcessRequest{
			AccountID:      identitySecurityProcessorTestAccountID,
			Operation:      "mfa_enroll",
			IdempotencyKey: "mfa-enroll-1",
		},
	)
	if err != nil || enrollResult.ConfirmationChallengeID != challenge {
		t.Fatalf("process MFA enrollment: result=%#v err=%v", enrollResult, err)
	}
	provisioning, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		IdentitySecuritySecretHandoffRequest{
			AccountID:      identitySecurityProcessorTestAccountID,
			Operation:      "mfa_enroll",
			IdempotencyKey: "mfa-enroll-1",
			HandoffID:      handoff,
		},
	)
	if err != nil || !strings.HasPrefix(provisioning.ProvisioningURI, "otpauth://totp/") {
		t.Fatalf("consume provisioning handoff: result=%#v err=%v", provisioning, err)
	}
	confirmResult, err := processor.ConfirmIdentitySecuritySecret(
		context.Background(),
		IdentitySecuritySecretConfirmRequest{
			AccountID:      identitySecurityProcessorTestAccountID,
			ChallengeID:    challenge,
			Code:           "123456",
			IdempotencyKey: "mfa-confirm-1",
		},
	)
	if err != nil || confirmResult.RecoveryCodeCount != len(recoveryCodes) {
		t.Fatalf("confirm MFA: result=%#v err=%v", confirmResult, err)
	}
	recovery, err := processor.ConsumeIdentitySecuritySecretHandoff(
		context.Background(),
		IdentitySecuritySecretHandoffRequest{
			AccountID:      identitySecurityProcessorTestAccountID,
			Operation:      "mfa_confirm",
			IdempotencyKey: "mfa-confirm-1",
			HandoffID:      handoff,
		},
	)
	if err != nil || len(recovery.RecoveryCodes) != len(recoveryCodes) {
		t.Fatalf("consume recovery handoff: result=%#v err=%v", recovery, err)
	}
	prepared, err := processor.PrepareIdentitySecuritySecretMutation(
		context.Background(),
		IdentitySecuritySecretMutationPrepareRequest{
			AccountID:                   identitySecurityProcessorTestAccountID,
			Operation:                   "mfa_recovery_consume",
			IdempotencyKey:              "mfa-recovery-consume-1",
			SecretRef:                   reference,
			SecretDigest:                digest,
			ExpectedRecoveryBatchDigest: recoveryDigest,
			ExpectedRecoveryCodeCount:   len(recoveryCodes),
			RecoveryCode:                recoveryCodes[0],
		},
	)
	if err != nil || prepared.RecoveryBatchDigest != nextRecoveryDigest ||
		prepared.RecoveryCodeCount != len(recoveryCodes)-1 {
		t.Fatalf("prepare recovery-code consume: result=%#v err=%v", prepared, err)
	}
	canceled, cancel := context.WithCancel(context.Background())
	cancel()
	if err := processor.FinalizeIdentitySecuritySecretMutation(
		canceled,
		IdentitySecuritySecretMutationFinalizeRequest{
			AccountID:      identitySecurityProcessorTestAccountID,
			Operation:      "mfa_recovery_consume",
			IdempotencyKey: "mfa-recovery-consume-1",
			FinalizeToken:  prepared.FinalizeToken,
		},
	); err != nil {
		t.Fatalf("finalize must survive caller cancellation: %v", err)
	}
	if err := processor.CleanupIdentitySecuritySecret(
		canceled,
		IdentitySecuritySecretCleanupRequest{
			AccountID:      identitySecurityProcessorTestAccountID,
			Operation:      "password_enroll",
			IdempotencyKey: "password-enroll-1",
			CleanupToken:   cleanup,
		},
	); err != nil {
		t.Fatalf("cleanup must survive caller cancellation: %v", err)
	}
	if strings.Join(paths, ",") !=
		strings.Join([]string{
			identitySecurityProcessorProcessPath,
			identitySecurityProcessorProcessPath,
			identitySecurityProcessorHandoffPath,
			identitySecurityProcessorConfirmPath,
			identitySecurityProcessorHandoffPath,
			identitySecurityProcessorPreparePath,
			identitySecurityProcessorFinalizePath,
			identitySecurityProcessorCleanupPath,
		}, ",") {
		t.Fatalf("unexpected processor call sequence: %v", paths)
	}
}

func TestHTTPIdentitySecuritySecretProcessorReadinessIsStrict(t *testing.T) {
	for name, response := range map[string]struct {
		status      int
		contentType string
		body        string
		ready       bool
	}{
		"ready": {
			status: http.StatusOK, contentType: "application/json",
			body: `{"schema_version":"` +
				IdentitySecurityProcessorSchemaVersion +
				`","status":"ready"}`,
			ready: true,
		},
		"wrong status": {
			status: http.StatusOK, contentType: "application/json",
			body: `{"schema_version":"` +
				IdentitySecurityProcessorSchemaVersion +
				`","status":"starting"}`,
		},
		"unknown field": {
			status: http.StatusOK, contentType: "application/json",
			body: `{"schema_version":"` +
				IdentitySecurityProcessorSchemaVersion +
				`","status":"ready","detail":"unsafe"}`,
		},
		"unavailable": {
			status:      http.StatusServiceUnavailable,
			contentType: "text/plain",
			body:        "DO-NOT-REFLECT-READINESS-BODY",
		},
	} {
		t.Run(name, func(t *testing.T) {
			server := httptest.NewTLSServer(http.HandlerFunc(
				func(writer http.ResponseWriter, request *http.Request) {
					if request.URL.Path != identitySecurityProcessorReadyPath ||
						request.Method != http.MethodGet ||
						request.Header.Get("Accept") != "application/json" {
						t.Fatalf("unexpected readiness request: %s %s", request.Method, request.URL.Path)
					}
					writer.Header().Set("Content-Type", response.contentType)
					writer.WriteHeader(response.status)
					_, _ = writer.Write([]byte(response.body))
				},
			))
			defer server.Close()
			processor, err := NewHTTPIdentitySecuritySecretProcessor(
				identitySecurityProcessorTestOptions(server, time.Second),
			)
			if err != nil {
				t.Fatalf("construct processor: %v", err)
			}
			readyErr := processor.Ready(context.Background())
			if response.ready && readyErr != nil {
				t.Fatalf("ready processor was rejected: %v", readyErr)
			}
			if !response.ready &&
				(!errors.Is(readyErr, ErrIdentitySecurityProcessorUnavailable) ||
					strings.Contains(readyErr.Error(), "DO-NOT-REFLECT")) {
				t.Fatalf("unsafe readiness response was accepted or exposed: %v", readyErr)
			}
		})
	}
}

func TestHTTPIdentitySecuritySecretProcessorRejectsUnsafeResponses(t *testing.T) {
	validPayload := `{"schema_version":"` + IdentitySecurityProcessorSchemaVersion +
		`","secret_ref":"isr_` + strings.Repeat("A", 24) +
		`","secret_digest":"` + strings.Repeat("a", 64) +
		`","key_version":"key-v1","cleanup_token":"isx_` +
		strings.Repeat("D", 24) + `"}`
	for name, response := range map[string]struct {
		status      int
		contentType string
		body        string
	}{
		"unknown field": {
			status: http.StatusOK, contentType: "application/json",
			body: strings.TrimSuffix(validPayload, "}") + `,"unexpected":true}`,
		},
		"trailing JSON": {
			status: http.StatusOK, contentType: "application/json",
			body: validPayload + `{}`,
		},
		"wrong media type": {
			status: http.StatusOK, contentType: "text/plain", body: validPayload,
		},
		"invalid reference": {
			status: http.StatusOK, contentType: "application/json",
			body: strings.Replace(validPayload, "isr_", "bad_", 1),
		},
		"upstream failure": {
			status:      http.StatusInternalServerError,
			contentType: "text/plain",
			body:        "DO-NOT-REFLECT-UPSTREAM-DETAIL",
		},
	} {
		t.Run(name, func(t *testing.T) {
			server := httptest.NewTLSServer(http.HandlerFunc(
				func(writer http.ResponseWriter, _ *http.Request) {
					writer.Header().Set("Content-Type", response.contentType)
					writer.WriteHeader(response.status)
					_, _ = writer.Write([]byte(response.body))
				},
			))
			defer server.Close()
			processor, err := NewHTTPIdentitySecuritySecretProcessor(
				identitySecurityProcessorTestOptions(server, time.Second),
			)
			if err != nil {
				t.Fatalf("construct processor: %v", err)
			}
			_, err = processor.ProcessIdentitySecuritySecret(
				context.Background(),
				IdentitySecuritySecretProcessRequest{
					AccountID:      identitySecurityProcessorTestAccountID,
					Operation:      "password_enroll",
					IdempotencyKey: "password-enroll-1",
					Password:       "TwelveChars1!",
				},
			)
			if !errors.Is(err, ErrIdentitySecurityProcessorUnavailable) ||
				strings.Contains(err.Error(), "DO-NOT-REFLECT") {
				t.Fatalf("unsafe response was not safely rejected: %v", err)
			}
		})
	}
}

func TestHTTPIdentitySecuritySecretProcessorRejectsOversizeRedirectAndTimeout(t *testing.T) {
	for name, handler := range map[string]http.Handler{
		"oversize": http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(strings.Repeat("x", maxIdentitySecurityProcessorResponseBytes+1)))
		}),
		"redirect": http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			http.Redirect(writer, request, "/other", http.StatusFound)
		}),
		"timeout": http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
			time.Sleep(30 * time.Millisecond)
			writer.Header().Set("Content-Type", "application/json")
			_, _ = writer.Write([]byte(`{}`))
		}),
	} {
		t.Run(name, func(t *testing.T) {
			server := httptest.NewTLSServer(handler)
			defer server.Close()
			timeout := time.Second
			if name == "timeout" {
				timeout = 5 * time.Millisecond
			}
			processor, err := NewHTTPIdentitySecuritySecretProcessor(
				identitySecurityProcessorTestOptions(server, timeout),
			)
			if err != nil {
				t.Fatalf("construct processor: %v", err)
			}
			_, err = processor.ProcessIdentitySecuritySecret(
				context.Background(),
				IdentitySecuritySecretProcessRequest{
					AccountID:      identitySecurityProcessorTestAccountID,
					Operation:      "password_enroll",
					IdempotencyKey: "password-enroll-1",
					Password:       "TwelveChars1!",
				},
			)
			if err == nil {
				t.Fatal("unsafe processor behavior was accepted")
			}
			if name == "timeout" && !errors.Is(err, context.DeadlineExceeded) {
				t.Fatalf("timeout did not preserve stable classification: %v", err)
			}
		})
	}
}

func TestIdentitySecuritySecretValidationRejectsInvalidPasswordTOTPAndRecovery(t *testing.T) {
	if validIdentitySecurityPassword("short") ||
		validIdentitySecurityPassword(strings.Repeat("a", 11)+"\n") ||
		!validIdentitySecurityPassword("TwelveChars1!") {
		t.Fatal("password policy validation is inconsistent")
	}
	for _, code := range []string{"12345", "1234567", "１２３４５６", "12345x"} {
		if validIdentitySecurityTOTPCode(code) {
			t.Fatalf("invalid TOTP code was accepted: %q", code)
		}
	}
	if validIdentitySecurityRecoveryCodes([]string{
		"A1BC-DEFG", "A1BC-DEFG", "C3DE-FGHJ",
		"D4EF-GHJK", "E5FG-HJKL", "F6GH-JKLM",
	}) {
		t.Fatal("duplicate recovery codes were accepted")
	}
}
