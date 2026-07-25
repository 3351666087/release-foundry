package ashrclone

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"
)

const (
	identitySecurityServiceTestOrganizationID = "11111111-1111-4111-8111-111111111111"
	identitySecurityServiceTestProjectID      = "22222222-2222-4222-8222-222222222222"
	identitySecurityServiceTestAccountID      = "33333333-3333-4333-8333-333333333333"
	identitySecurityServiceTestSessionID      = "44444444-4444-4444-8444-444444444444"
)

type identitySecurityServiceTestProcessor struct {
	processResult IdentitySecuritySecretProcessResult
	processErr    error
	confirmResult IdentitySecuritySecretConfirmResult
	confirmErr    error
	handoffs      map[string]IdentitySecuritySecretHandoff
	handoffErr    error
	processCalls  []IdentitySecuritySecretProcessRequest
	confirmCalls  []IdentitySecuritySecretConfirmRequest
	handoffCalls  []IdentitySecuritySecretHandoffRequest
	cleanupCalls  []IdentitySecuritySecretCleanupRequest
	events        *[]string
}

func (processor *identitySecurityServiceTestProcessor) ProcessIdentitySecuritySecret(
	_ context.Context,
	request IdentitySecuritySecretProcessRequest,
) (IdentitySecuritySecretProcessResult, error) {
	processor.processCalls = append(processor.processCalls, request)
	if processor.events != nil {
		*processor.events = append(*processor.events, "process")
	}
	return processor.processResult, processor.processErr
}

func (processor *identitySecurityServiceTestProcessor) ConfirmIdentitySecuritySecret(
	_ context.Context,
	request IdentitySecuritySecretConfirmRequest,
) (IdentitySecuritySecretConfirmResult, error) {
	processor.confirmCalls = append(processor.confirmCalls, request)
	if processor.events != nil {
		*processor.events = append(*processor.events, "confirm")
	}
	return processor.confirmResult, processor.confirmErr
}

func (processor *identitySecurityServiceTestProcessor) ConsumeIdentitySecuritySecretHandoff(
	_ context.Context,
	request IdentitySecuritySecretHandoffRequest,
) (IdentitySecuritySecretHandoff, error) {
	processor.handoffCalls = append(processor.handoffCalls, request)
	if processor.events != nil {
		*processor.events = append(*processor.events, "handoff")
	}
	return processor.handoffs[request.Operation], processor.handoffErr
}

func (processor *identitySecurityServiceTestProcessor) CleanupIdentitySecuritySecret(
	_ context.Context,
	request IdentitySecuritySecretCleanupRequest,
) error {
	processor.cleanupCalls = append(processor.cleanupCalls, request)
	if processor.events != nil {
		*processor.events = append(*processor.events, "cleanup")
	}
	return nil
}

type identitySecurityServiceTestIssuer struct {
	issueErr      error
	overrideIssue *IdentitySecurityIssuedTicket
	issueCalls    []IdentitySecurityTicketIssueRequest
	cancelCalls   int
	events        *[]string
}

func (issuer *identitySecurityServiceTestIssuer) IssueIdentitySecurityMutationTicket(
	_ context.Context,
	request IdentitySecurityTicketIssueRequest,
) (IdentitySecurityIssuedTicket, error) {
	issuer.issueCalls = append(issuer.issueCalls, request)
	if issuer.events != nil {
		*issuer.events = append(*issuer.events, "issue")
	}
	if issuer.issueErr != nil {
		return IdentitySecurityIssuedTicket{}, issuer.issueErr
	}
	if issuer.overrideIssue != nil {
		return *issuer.overrideIssue, nil
	}
	return IdentitySecurityIssuedTicket{
		TicketID:      strings.Repeat("c", 64),
		ReceiptID:     strings.Repeat("d", 64),
		ContextDigest: request.ContextDigest,
		ExpiresAt:     request.ExpiresAt,
	}, nil
}

func (issuer *identitySecurityServiceTestIssuer) CancelIdentitySecurityMutationTicket(
	_ context.Context,
	_ IdentitySecurityTicketIssueRequest,
	_ IdentitySecurityIssuedTicket,
) error {
	issuer.cancelCalls++
	if issuer.events != nil {
		*issuer.events = append(*issuer.events, "cancel")
	}
	return nil
}

type identitySecurityServiceTestStore struct {
	result    IdentitySecurityHTTPMutationResultDTO
	err       error
	mutations []IdentitySecurityMutation
	events    *[]string
}

func (store *identitySecurityServiceTestStore) GetIdentitySecurityPosture(
	context.Context,
	string,
) (IdentitySecurityHTTPPostureDTO, error) {
	return IdentitySecurityHTTPPostureDTO{}, nil
}

func (store *identitySecurityServiceTestStore) MutateIdentitySecurity(
	_ context.Context,
	mutation IdentitySecurityMutation,
) (IdentitySecurityHTTPMutationResultDTO, error) {
	store.mutations = append(store.mutations, mutation)
	if store.events != nil {
		*store.events = append(*store.events, "mutate")
	}
	return store.result, store.err
}

func newIdentitySecurityServiceTestSubject(
	t *testing.T,
	processor IdentitySecuritySecretProcessor,
	issuer IdentitySecurityTicketIssuer,
	store IdentitySecurityHTTPStore,
	now time.Time,
) *IdentitySecurityService {
	t.Helper()
	service, err := NewIdentitySecurityService(IdentitySecurityServiceOptions{
		Processor:      processor,
		TicketIssuer:   issuer,
		MutationStore:  store,
		OrganizationID: identitySecurityServiceTestOrganizationID,
		ProjectID:      identitySecurityServiceTestProjectID,
		TicketTTL:      4 * time.Minute,
		Now:            func() time.Time { return now },
	})
	if err != nil {
		t.Fatalf("construct identity security service: %v", err)
	}
	return service
}

func identitySecurityServiceTestSession() IdentityHTTPSession {
	return IdentityHTTPSession{
		AccountID:     identitySecurityServiceTestAccountID,
		ActorID:       identitySecurityServiceTestAccountID,
		SessionID:     identitySecurityServiceTestSessionID,
		SessionDigest: strings.Repeat("e", 64),
	}
}

func identitySecurityServiceTestProcessResult() IdentitySecuritySecretProcessResult {
	return IdentitySecuritySecretProcessResult{
		SecretRef:    "isr_" + strings.Repeat("A", 24),
		SecretDigest: strings.Repeat("a", 64),
		KeyVersion:   "key-v1",
		CleanupToken: "isx_" + strings.Repeat("D", 24),
	}
}

func TestIdentitySecurityServicePasswordFlowIsCanonicalIdempotentAndSecretSafe(t *testing.T) {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	processor := &identitySecurityServiceTestProcessor{
		processResult: identitySecurityServiceTestProcessResult(),
		handoffs:      map[string]IdentitySecuritySecretHandoff{},
	}
	issuer := &identitySecurityServiceTestIssuer{}
	store := &identitySecurityServiceTestStore{
		result: IdentitySecurityHTTPMutationResultDTO{
			PasswordStatus:           "set",
			SecurityVersion:          2,
			SessionsRevoked:          3,
			ReauthenticationRequired: true,
		},
	}
	service := newIdentitySecurityServiceTestSubject(
		t, processor, issuer, store, now,
	)
	request := IdentitySecurityBeginRequest{
		Operation:      "password_enroll",
		IdempotencyKey: "password-enroll-1",
		Password:       "TwelveChars1!",
	}
	first, err := service.Begin(
		context.Background(),
		identitySecurityServiceTestSession(),
		request,
	)
	if err != nil {
		t.Fatalf("begin password enrollment: %v", err)
	}
	second, err := service.Begin(
		context.Background(),
		identitySecurityServiceTestSession(),
		request,
	)
	if err != nil {
		t.Fatalf("retry password enrollment: %v", err)
	}
	if !reflect.DeepEqual(first, second) ||
		first.PasswordStatus != "set" ||
		!first.TwoFactorOptional ||
		!first.TwoFactorRecommended ||
		!first.ReauthenticationRequired {
		t.Fatalf("unexpected public result: %#v %#v", first, second)
	}
	if len(issuer.issueCalls) != 2 || len(store.mutations) != 2 ||
		issuer.issueCalls[0].ContextDigest != issuer.issueCalls[1].ContextDigest ||
		issuer.issueCalls[0].AccountID != identitySecurityServiceTestAccountID ||
		issuer.issueCalls[0].ActorID != identitySecurityServiceTestAccountID ||
		issuer.issueCalls[0].SessionID != identitySecurityServiceTestSessionID {
		t.Fatalf("canonical/idempotency binding was lost: %#v", issuer.issueCalls)
	}
	encoded, err := json.Marshal(first)
	if err != nil {
		t.Fatalf("marshal public result: %v", err)
	}
	for _, forbidden := range []string{
		"secret_ref", "secret_digest", "ticket_id", "receipt",
		processor.processResult.SecretRef,
		processor.processResult.SecretDigest,
		strings.Repeat("c", 64),
		strings.Repeat("d", 64),
	} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("public result exposed internal material %q: %s", forbidden, encoded)
		}
	}
}

func TestIdentitySecurityServiceMFAEnrollmentAndConfirmationPreserveOneUseHandoff(t *testing.T) {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	events := []string{}
	processResult := identitySecurityServiceTestProcessResult()
	processResult.ConfirmationChallengeID = "isc_" + strings.Repeat("B", 24)
	processResult.HandoffID = "ish_" + strings.Repeat("C", 24)
	processor := &identitySecurityServiceTestProcessor{
		processResult: processResult,
		confirmResult: IdentitySecuritySecretConfirmResult{
			RecoveryBatchDigest: strings.Repeat("b", 64),
			RecoveryCodeCount:   6,
			KeyVersion:          "key-v1",
			HandoffID:           "ish_" + strings.Repeat("E", 24),
			CleanupToken:        "isx_" + strings.Repeat("F", 24),
		},
		handoffs: map[string]IdentitySecuritySecretHandoff{
			"mfa_enroll": {
				ProvisioningURI: "otpauth://totp/Ashr:test?secret=ABCDEF234567",
			},
			"mfa_confirm": {
				RecoveryCodes: []string{
					"A1BC-DEFG", "B2CD-EFGH", "C3DE-FGHJ",
					"D4EF-GHJK", "E5FG-HJKL", "F6GH-JKLM",
				},
			},
		},
		events: &events,
	}
	issuer := &identitySecurityServiceTestIssuer{events: &events}
	store := &identitySecurityServiceTestStore{
		result: IdentitySecurityHTTPMutationResultDTO{
			TwoFactorStatus:      "pending",
			ConfirmationRequired: true,
			SecurityVersion:      3,
		},
		events: &events,
	}
	service := newIdentitySecurityServiceTestSubject(
		t, processor, issuer, store, now,
	)
	begin, err := service.Begin(
		context.Background(),
		identitySecurityServiceTestSession(),
		IdentitySecurityBeginRequest{
			Operation:      "mfa_enroll",
			IdempotencyKey: "mfa-enroll-1",
		},
	)
	if err != nil {
		t.Fatalf("begin MFA enrollment: %v", err)
	}
	if !begin.ConfirmationRequired ||
		begin.ConfirmationChallengeID != processResult.ConfirmationChallengeID ||
		!strings.HasPrefix(begin.ProvisioningURI, "otpauth://totp/") {
		t.Fatalf("unsafe/incomplete MFA begin result: %#v", begin)
	}
	store.result = IdentitySecurityHTTPMutationResultDTO{
		TwoFactorStatus:          "enabled",
		RecoveryCodesRemaining:   6,
		SecurityVersion:          4,
		SessionsRevoked:          2,
		ReauthenticationRequired: true,
	}
	confirmed, err := service.Confirm(
		context.Background(),
		identitySecurityServiceTestSession(),
		IdentitySecurityConfirmRequest{
			IdempotencyKey: "mfa-confirm-1",
			ChallengeID:    processResult.ConfirmationChallengeID,
			Code:           "123456",
		},
	)
	if err != nil {
		t.Fatalf("confirm MFA enrollment: %v", err)
	}
	if confirmed.TwoFactorStatus != "enabled" ||
		len(confirmed.RecoveryCodes) != 6 ||
		!confirmed.ReauthenticationRequired {
		t.Fatalf("incomplete MFA confirm result: %#v", confirmed)
	}
	if strings.Join(events, ",") !=
		"process,issue,mutate,handoff,confirm,issue,mutate,handoff" {
		t.Fatalf("secret/DB/handoff ordering changed: %v", events)
	}
	if len(processor.handoffCalls) != 2 ||
		processor.handoffCalls[0].Operation != "mfa_enroll" ||
		processor.handoffCalls[1].Operation != "mfa_confirm" {
		t.Fatalf("handoff scope was not explicit: %#v", processor.handoffCalls)
	}
}

func TestIdentitySecurityServiceCompensatesIssuerAndMutationFailuresExactlyOnce(t *testing.T) {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	for name, testCase := range map[string]struct {
		issueErr    error
		mutationErr error
		wantCancel  int
	}{
		"issuer failure": {
			issueErr: ErrIdentitySecurityUnavailable,
		},
		"mutation rejection": {
			mutationErr: ErrIdentitySecurityRejected,
			wantCancel:  1,
		},
		"mutation unavailable": {
			mutationErr: ErrIdentitySecurityUnavailable,
			wantCancel:  1,
		},
	} {
		t.Run(name, func(t *testing.T) {
			events := []string{}
			processor := &identitySecurityServiceTestProcessor{
				processResult: identitySecurityServiceTestProcessResult(),
				handoffs:      map[string]IdentitySecuritySecretHandoff{},
				events:        &events,
			}
			issuer := &identitySecurityServiceTestIssuer{
				issueErr: testCase.issueErr,
				events:   &events,
			}
			store := &identitySecurityServiceTestStore{
				result: IdentitySecurityHTTPMutationResultDTO{
					PasswordStatus:           "set",
					ReauthenticationRequired: true,
				},
				err:    testCase.mutationErr,
				events: &events,
			}
			service := newIdentitySecurityServiceTestSubject(
				t, processor, issuer, store, now,
			)
			_, err := service.Begin(
				context.Background(),
				identitySecurityServiceTestSession(),
				IdentitySecurityBeginRequest{
					Operation:      "password_change",
					IdempotencyKey: "password-change-1",
					Password:       "TwelveChars1!",
				},
			)
			if err == nil {
				t.Fatal("dependency failure was accepted")
			}
			if len(processor.cleanupCalls) != 1 ||
				issuer.cancelCalls != testCase.wantCancel {
				t.Fatalf(
					"compensation was not exactly once: cleanup=%d cancel=%d events=%v",
					len(processor.cleanupCalls),
					issuer.cancelCalls,
					events,
				)
			}
		})
	}
}

func TestIdentitySecurityServiceRejectsInvalidDependencyOutputsAndSessionInjection(t *testing.T) {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	validProcess := identitySecurityServiceTestProcessResult()
	for name, testCase := range map[string]struct {
		process IdentitySecuritySecretProcessResult
		issued  *IdentitySecurityIssuedTicket
		result  IdentitySecurityHTTPMutationResultDTO
	}{
		"invalid processor ref": {
			process: func() IdentitySecuritySecretProcessResult {
				result := validProcess
				result.SecretRef = "invalid"
				return result
			}(),
			result: IdentitySecurityHTTPMutationResultDTO{
				PasswordStatus:           "set",
				ReauthenticationRequired: true,
			},
		},
		"invalid issuer context": {
			process: validProcess,
			issued: &IdentitySecurityIssuedTicket{
				TicketID:      strings.Repeat("c", 64),
				ReceiptID:     strings.Repeat("d", 64),
				ContextDigest: strings.Repeat("f", 64),
				ExpiresAt:     now.Add(time.Minute),
			},
			result: IdentitySecurityHTTPMutationResultDTO{
				PasswordStatus:           "set",
				ReauthenticationRequired: true,
			},
		},
		"invalid store projection": {
			process: validProcess,
			result:  IdentitySecurityHTTPMutationResultDTO{PasswordStatus: "set"},
		},
	} {
		t.Run(name, func(t *testing.T) {
			processor := &identitySecurityServiceTestProcessor{
				processResult: testCase.process,
				handoffs:      map[string]IdentitySecuritySecretHandoff{},
			}
			issuer := &identitySecurityServiceTestIssuer{
				overrideIssue: testCase.issued,
			}
			store := &identitySecurityServiceTestStore{result: testCase.result}
			service := newIdentitySecurityServiceTestSubject(
				t, processor, issuer, store, now,
			)
			_, err := service.Begin(
				context.Background(),
				identitySecurityServiceTestSession(),
				IdentitySecurityBeginRequest{
					Operation:      "password_change",
					IdempotencyKey: "password-change-1",
					Password:       "TwelveChars1!",
				},
			)
			if !errors.Is(err, ErrIdentitySecurityUnavailable) {
				t.Fatalf("invalid dependency output was not fail-closed: %v", err)
			}
			if len(processor.cleanupCalls) != 1 {
				t.Fatalf("invalid dependency output was not cleaned up: %#v", processor.cleanupCalls)
			}
		})
	}

	processor := &identitySecurityServiceTestProcessor{
		processResult: validProcess,
		handoffs:      map[string]IdentitySecuritySecretHandoff{},
	}
	issuer := &identitySecurityServiceTestIssuer{}
	store := &identitySecurityServiceTestStore{}
	service := newIdentitySecurityServiceTestSubject(
		t, processor, issuer, store, now,
	)
	for name, session := range map[string]IdentityHTTPSession{
		"actor mismatch": func() IdentityHTTPSession {
			session := identitySecurityServiceTestSession()
			session.ActorID = identitySecurityServiceTestProjectID
			return session
		}(),
		"revoked": func() IdentityHTTPSession {
			session := identitySecurityServiceTestSession()
			session.Revoked = true
			return session
		}(),
		"missing digest": func() IdentityHTTPSession {
			session := identitySecurityServiceTestSession()
			session.SessionDigest = ""
			return session
		}(),
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := service.Begin(
				context.Background(),
				session,
				IdentitySecurityBeginRequest{
					Operation:      "password_change",
					IdempotencyKey: "password-change-1",
					Password:       "TwelveChars1!",
				},
			); !errors.Is(err, ErrIdentitySecurityRejected) {
				t.Fatalf("invalid canonical session was accepted: %v", err)
			}
		})
	}
	if _, err := service.Begin(
		nil,
		identitySecurityServiceTestSession(),
		IdentitySecurityBeginRequest{
			Operation:      "password_change",
			IdempotencyKey: "password-change-1",
			Password:       "TwelveChars1!",
		},
	); !errors.Is(err, ErrIdentitySecurityRejected) {
		t.Fatalf("nil context was accepted: %v", err)
	}
	if len(processor.processCalls) != 0 {
		t.Fatalf("rejected sessions reached secret processor: %#v", processor.processCalls)
	}
}

func TestIdentitySecurityServiceHandoffReplayFailureDoesNotExposeOrDeleteCommittedSecret(t *testing.T) {
	now := time.Date(2026, 7, 24, 8, 0, 0, 0, time.UTC)
	processResult := identitySecurityServiceTestProcessResult()
	processResult.ConfirmationChallengeID = "isc_" + strings.Repeat("B", 24)
	processResult.HandoffID = "ish_" + strings.Repeat("C", 24)
	processor := &identitySecurityServiceTestProcessor{
		processResult: processResult,
		handoffs:      map[string]IdentitySecuritySecretHandoff{},
		handoffErr:    ErrIdentitySecurityProcessorRejected,
	}
	issuer := &identitySecurityServiceTestIssuer{}
	store := &identitySecurityServiceTestStore{
		result: IdentitySecurityHTTPMutationResultDTO{
			TwoFactorStatus:      "pending",
			ConfirmationRequired: true,
		},
	}
	service := newIdentitySecurityServiceTestSubject(
		t, processor, issuer, store, now,
	)
	result, err := service.Begin(
		context.Background(),
		identitySecurityServiceTestSession(),
		IdentitySecurityBeginRequest{
			Operation:      "mfa_enroll",
			IdempotencyKey: "mfa-enroll-1",
		},
	)
	if !errors.Is(err, ErrIdentitySecurityRejected) {
		t.Fatalf("replayed handoff was not rejected: result=%#v err=%v", result, err)
	}
	if issuer.cancelCalls != 0 || len(processor.cleanupCalls) != 0 ||
		len(store.mutations) != 1 {
		t.Fatalf(
			"committed secret was unsafely compensated: cancel=%d cleanup=%d mutations=%d",
			issuer.cancelCalls,
			len(processor.cleanupCalls),
			len(store.mutations),
		)
	}
}
