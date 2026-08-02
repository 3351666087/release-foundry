package releasefoundry

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"
)

type recordingIdentityCredentialLinkCoordinator struct {
	calls   int
	command IdentityCredentialLinkCommand
	now     time.Time
	result  IdentityCredentialLinkResultDTO
	err     error
}

func (coordinator *recordingIdentityCredentialLinkCoordinator) CompleteIdentityCredentialLink(
	_ context.Context,
	command IdentityCredentialLinkCommand,
	now time.Time,
) (IdentityCredentialLinkResultDTO, error) {
	coordinator.calls++
	coordinator.command = command
	coordinator.now = now
	return coordinator.result, coordinator.err
}

func validIdentityCredentialLinkCommand() IdentityCredentialLinkCommand {
	return IdentityCredentialLinkCommand{
		AccountID:        "account-1",
		ActorID:          "account-1",
		SessionID:        "session-1",
		SessionDigest:    strings.Repeat("a", 64),
		Provider:         IdentityProviderGoogle,
		TenantID:         "tenant-1",
		ProjectID:        "project-1",
		ProofReceiptID:   "ipr_server_owned_receipt",
		MutationTicketID: strings.Repeat("b", 64),
		StepUpReceiptID:  strings.Repeat("c", 64),
		IdempotencyKey:   "credential-link-0001",
	}
}

func validIdentityCredentialLinkResult(now time.Time) IdentityCredentialLinkResultDTO {
	return IdentityCredentialLinkResultDTO{
		AccountID: "account-1",
		Credential: IdentityCredentialDTO{
			SchemaVersion: UnifiedIdentitySchemaVersion,
			CredentialID:  "credential-1",
			Kind:          IdentityCredentialOAuth,
			Provider:      IdentityProviderGoogle,
			Verified:      true,
			CanLogin:      true,
			LinkedAt:      now,
		},
		CredentialAdded: true,
		SecurityPosture: IdentitySecurityPostureDTO{
			PrimaryEmail: IdentityEmailPostureDTO{Present: true, Verified: true, Source: IdentityProviderGoogle},
			Password:     IdentityPasswordPostureDTO{Status: "absent"},
			TwoFactor:    IdentityTwoFactorPostureDTO{Status: "not_enabled", Optional: true, Recommended: true},
		},
		LinkedAt: now,
	}
}

func TestIdentityCredentialLinkRejectsUntrustedCommandsBeforeCoordinator(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	tests := map[string]func(*IdentityCredentialLinkCommand){
		"account missing":     func(command *IdentityCredentialLinkCommand) { command.AccountID = "" },
		"actor missing":       func(command *IdentityCredentialLinkCommand) { command.ActorID = "" },
		"actor mismatch":      func(command *IdentityCredentialLinkCommand) { command.ActorID = "account-2" },
		"session missing":     func(command *IdentityCredentialLinkCommand) { command.SessionID = "" },
		"session digest":      func(command *IdentityCredentialLinkCommand) { command.SessionDigest = "caller-session" },
		"tenant missing":      func(command *IdentityCredentialLinkCommand) { command.TenantID = "" },
		"project missing":     func(command *IdentityCredentialLinkCommand) { command.ProjectID = "" },
		"provider missing":    func(command *IdentityCredentialLinkCommand) { command.Provider = "" },
		"provider unknown":    func(command *IdentityCredentialLinkCommand) { command.Provider = "unknown" },
		"proof missing":       func(command *IdentityCredentialLinkCommand) { command.ProofReceiptID = "" },
		"proof not opaque":    func(command *IdentityCredentialLinkCommand) { command.ProofReceiptID = "caller-proof" },
		"mutation missing":    func(command *IdentityCredentialLinkCommand) { command.MutationTicketID = "" },
		"mutation malformed":  func(command *IdentityCredentialLinkCommand) { command.MutationTicketID = "ticket" },
		"step-up missing":     func(command *IdentityCredentialLinkCommand) { command.StepUpReceiptID = "" },
		"step-up malformed":   func(command *IdentityCredentialLinkCommand) { command.StepUpReceiptID = "step-up" },
		"idempotency missing": func(command *IdentityCredentialLinkCommand) { command.IdempotencyKey = "" },
		"idempotency invalid": func(command *IdentityCredentialLinkCommand) { command.IdempotencyKey = "bad key" },
	}
	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			coordinator := &recordingIdentityCredentialLinkCoordinator{
				result: validIdentityCredentialLinkResult(now),
			}
			service, err := NewIdentityCredentialLinkService(coordinator, func() time.Time { return now })
			if err != nil {
				t.Fatal(err)
			}
			command := validIdentityCredentialLinkCommand()
			mutate(&command)
			if _, err := service.Complete(context.Background(), command); err == nil {
				t.Fatal("untrusted credential-link command was accepted")
			}
			if coordinator.calls != 0 {
				t.Fatalf("invalid command reached coordinator %d times", coordinator.calls)
			}
		})
	}
}

func TestIdentityCredentialLinkForwardsNormalizedCommandExactlyOnce(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.FixedZone("CST", 8*60*60))
	coordinator := &recordingIdentityCredentialLinkCoordinator{
		result: validIdentityCredentialLinkResult(now),
	}
	service, err := NewIdentityCredentialLinkService(coordinator, func() time.Time { return now })
	if err != nil {
		t.Fatal(err)
	}
	command := validIdentityCredentialLinkCommand()
	command.AccountID = " account-1 "
	command.ActorID = " account-1 "
	command.Provider = " GOOGLE "
	command.TenantID = " tenant-1 "
	command.ProjectID = " project-1 "

	result, err := service.Complete(context.Background(), command)
	if err != nil {
		t.Fatal(err)
	}
	if coordinator.calls != 1 {
		t.Fatalf("coordinator calls = %d, want 1", coordinator.calls)
	}
	if coordinator.command.AccountID != "account-1" ||
		coordinator.command.ActorID != "account-1" ||
		coordinator.command.Provider != IdentityProviderGoogle ||
		coordinator.command.TenantID != "tenant-1" ||
		coordinator.command.ProjectID != "project-1" {
		t.Fatalf("command was not normalized: %#v", coordinator.command)
	}
	if !coordinator.now.Equal(now.UTC()) {
		t.Fatalf("coordinator time = %s, want %s", coordinator.now, now.UTC())
	}
	if result.SchemaVersion != IdentityCredentialLinkSchemaVersion ||
		result.AccountID != "account-1" ||
		result.Credential.Provider != IdentityProviderGoogle ||
		!result.LinkedAt.Equal(now.UTC()) {
		t.Fatalf("unexpected public result: %#v", result)
	}
}

func TestIdentityCredentialLinkPropagatesCoordinatorFailure(t *testing.T) {
	expected := errors.New("atomic transaction rolled back")
	coordinator := &recordingIdentityCredentialLinkCoordinator{err: expected}
	service, err := NewIdentityCredentialLinkService(coordinator, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := service.Complete(context.Background(), validIdentityCredentialLinkCommand()); !errors.Is(err, expected) {
		t.Fatalf("coordinator failure = %v, want %v", err, expected)
	}
	if coordinator.calls != 1 {
		t.Fatalf("coordinator calls = %d, want 1", coordinator.calls)
	}
}

func TestIdentityCredentialLinkRejectsUnsafeOrMismatchedResult(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	tests := map[string]func(*IdentityCredentialLinkResultDTO){
		"account mismatch":   func(result *IdentityCredentialLinkResultDTO) { result.AccountID = "account-2" },
		"credential missing": func(result *IdentityCredentialLinkResultDTO) { result.Credential.CredentialID = "" },
		"provider mismatch":  func(result *IdentityCredentialLinkResultDTO) { result.Credential.Provider = IdentityProviderGitHub },
		"not verified":       func(result *IdentityCredentialLinkResultDTO) { result.Credential.Verified = false },
		"linked at missing":  func(result *IdentityCredentialLinkResultDTO) { result.LinkedAt = time.Time{} },
	}
	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			result := validIdentityCredentialLinkResult(now)
			mutate(&result)
			coordinator := &recordingIdentityCredentialLinkCoordinator{result: result}
			service, err := NewIdentityCredentialLinkService(coordinator, func() time.Time { return now })
			if err != nil {
				t.Fatal(err)
			}
			if _, err := service.Complete(context.Background(), validIdentityCredentialLinkCommand()); err == nil {
				t.Fatal("invalid coordinator result was accepted")
			}
		})
	}
}

func TestIdentityCredentialLinkPublicResultCannotLeakAuthorizationOrIdentitySecrets(t *testing.T) {
	now := time.Date(2026, 7, 14, 8, 0, 0, 0, time.UTC)
	raw, err := json.Marshal(validIdentityCredentialLinkResult(now))
	if err != nil {
		t.Fatal(err)
	}
	serialized := string(raw)
	for _, forbidden := range []string{
		`"proof_receipt_id"`, `"mutation_ticket_id"`, `"step_up_receipt_id"`,
		`"session_digest"`, `"identifier"`, `"provider_subject"`,
		`"oauth_token"`, `"oauth_code"`, `"password_value"`, `"otp"`,
	} {
		if strings.Contains(serialized, forbidden) {
			t.Fatalf("public result leaked forbidden field %q: %s", forbidden, serialized)
		}
	}
}

func TestIdentityCredentialLinkContractDoesNotActivateA3Routes(t *testing.T) {
	for _, entry := range GoRouteManifestEntries() {
		if strings.Contains(entry.Route, "/identities/") &&
			(strings.HasSuffix(entry.Route, "/link/start") ||
				strings.HasSuffix(entry.Route, "/link/complete")) {
			t.Fatalf("proposed credential-link route became active: %#v", entry)
		}
	}
}
