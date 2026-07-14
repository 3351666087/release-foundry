package ashrclone

import (
	"bytes"
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/lib/pq"
)

var _ IdentitySecurityHTTPStore = (*ProductionIdentityStore)(nil)
var _ IdentitySecurityTicketResolver = (*ProductionIdentityStore)(nil)

type identitySecurityTicketProjection struct {
	TicketID        string    `json:"ticket_id"`
	AccountID       string    `json:"account_id"`
	Operation       string    `json:"operation"`
	StepUpReceiptID string    `json:"step_up_receipt_id"`
	ExpiresAt       time.Time `json:"expires_at"`
}

// ResolveIdentitySecurityMutationTicket asks PostgreSQL for only the public
// authorization envelope. Secret refs, keyed digests, recovery material and
// private receipt state remain inside migration 018's SECURITY DEFINER
// authority.
func (store *ProductionIdentityStore) ResolveIdentitySecurityMutationTicket(
	ctx context.Context,
	ticketID string,
	stepUpReceiptID string,
	operation string,
) (IdentitySecurityMutationTicket, error) {
	if store == nil || store.db == nil || store.now == nil {
		return IdentitySecurityMutationTicket{}, ErrIdentitySecurityUnavailable
	}
	ticketID = strings.TrimSpace(ticketID)
	stepUpReceiptID = strings.TrimSpace(stepUpReceiptID)
	operation = strings.TrimSpace(operation)
	if !validIdentitySecurityDigest(ticketID) ||
		!validIdentitySecurityDigest(stepUpReceiptID) ||
		!validIdentitySecurityOperation(operation) {
		return IdentitySecurityMutationTicket{}, ErrIdentitySecurityRejected
	}
	queryCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	tx, err := store.db.BeginTx(queryCtx, &sql.TxOptions{
		Isolation: sql.LevelReadCommitted,
		ReadOnly:  true,
	})
	if err != nil {
		return IdentitySecurityMutationTicket{}, identitySecurityDatabaseError(err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if err = configureIdentitySecurityTransaction(queryCtx, tx, store); err != nil {
		return IdentitySecurityMutationTicket{}, identitySecurityDatabaseError(err)
	}
	var raw []byte
	if err = tx.QueryRowContext(queryCtx, `
SELECT a1_resolve_identity_security_mutation_ticket($1,$2,$3,$4)
`, ticketID, stepUpReceiptID, operation, store.now().UTC()).Scan(&raw); err != nil {
		return IdentitySecurityMutationTicket{}, identitySecurityDatabaseError(err)
	}
	var projection identitySecurityTicketProjection
	if len(raw) == 0 || decodeIdentitySecurityJSON(raw, &projection) != nil ||
		projection.TicketID != ticketID ||
		projection.StepUpReceiptID != stepUpReceiptID ||
		projection.Operation != operation ||
		!validPostgresIdentityVerificationUUID(projection.AccountID) ||
		projection.ExpiresAt.IsZero() {
		return IdentitySecurityMutationTicket{}, ErrIdentitySecurityUnavailable
	}
	if err = tx.Commit(); err != nil {
		return IdentitySecurityMutationTicket{}, identitySecurityDatabaseError(err)
	}
	committed = true
	return IdentitySecurityMutationTicket{
		TicketID:      projection.TicketID,
		AccountID:     projection.AccountID,
		Operation:     projection.Operation,
		ReceiptDigest: projection.StepUpReceiptID,
		ExpiresAt:     projection.ExpiresAt.UTC(),
	}, nil
}

// GetIdentitySecurityPosture returns only migration 018's public-safe
// projection. Vault references, keyed digests, receipts, and recovery material
// are neither selected nor decoded by this boundary.
func (store *ProductionIdentityStore) GetIdentitySecurityPosture(
	ctx context.Context,
	accountID string,
) (IdentitySecurityHTTPPostureDTO, error) {
	if store == nil || store.db == nil {
		return IdentitySecurityHTTPPostureDTO{}, ErrIdentitySecurityUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	if !validPostgresIdentityVerificationUUID(accountID) {
		return IdentitySecurityHTTPPostureDTO{}, ErrIdentitySecurityRejected
	}
	queryCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	tx, err := store.db.BeginTx(queryCtx, &sql.TxOptions{
		Isolation: sql.LevelReadCommitted,
		ReadOnly:  true,
	})
	if err != nil {
		return IdentitySecurityHTTPPostureDTO{}, identitySecurityDatabaseError(err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if err = configureIdentitySecurityTransaction(queryCtx, tx, store); err != nil {
		return IdentitySecurityHTTPPostureDTO{}, identitySecurityDatabaseError(err)
	}
	var raw []byte
	if err = tx.QueryRowContext(queryCtx, `
SELECT a1_project_account_security($1::uuid)
`, accountID).Scan(&raw); err != nil {
		return IdentitySecurityHTTPPostureDTO{}, identitySecurityDatabaseError(err)
	}
	var posture IdentitySecurityHTTPPostureDTO
	if len(raw) == 0 || decodeIdentitySecurityJSON(raw, &posture) != nil ||
		!validIdentitySecurityPosture(posture) {
		return IdentitySecurityHTTPPostureDTO{}, ErrIdentitySecurityUnavailable
	}
	if err = tx.Commit(); err != nil {
		return IdentitySecurityHTTPPostureDTO{}, identitySecurityDatabaseError(err)
	}
	committed = true
	return posture, nil
}

// MutateIdentitySecurity routes every trusted mutation through migration 018's
// single atomic SECURITY DEFINER authority. The Go process never selects or
// receives secret references, keyed digests, or recovery material.
func (store *ProductionIdentityStore) MutateIdentitySecurity(
	ctx context.Context,
	mutation IdentitySecurityMutation,
) (IdentitySecurityHTTPMutationResultDTO, error) {
	if store == nil || store.db == nil || store.now == nil {
		return IdentitySecurityHTTPMutationResultDTO{}, ErrIdentitySecurityUnavailable
	}
	now := store.now().UTC()
	if !validIdentitySecurityMutation(mutation, now) {
		return IdentitySecurityHTTPMutationResultDTO{}, ErrIdentitySecurityRejected
	}
	queryCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	tx, err := store.db.BeginTx(queryCtx, &sql.TxOptions{Isolation: sql.LevelReadCommitted})
	if err != nil {
		return IdentitySecurityHTTPMutationResultDTO{}, identitySecurityDatabaseError(err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if err = configureIdentitySecurityTransaction(queryCtx, tx, store); err != nil {
		return IdentitySecurityHTTPMutationResultDTO{}, identitySecurityDatabaseError(err)
	}
	requestFingerprint := identitySecurityRequestFingerprint(mutation)
	var raw []byte
	err = tx.QueryRowContext(queryCtx, `
SELECT a1_execute_identity_security_mutation($1,$2,$3)
`, mutation.Ticket.TicketID, mutation.IdempotencyKey, requestFingerprint).Scan(&raw)
	if err != nil {
		return IdentitySecurityHTTPMutationResultDTO{}, identitySecurityDatabaseError(err)
	}
	var result IdentitySecurityHTTPMutationResultDTO
	if len(raw) == 0 || decodeIdentitySecurityJSON(raw, &result) != nil ||
		!validIdentitySecurityMutationResult(mutation.Operation, result) {
		return IdentitySecurityHTTPMutationResultDTO{}, ErrIdentitySecurityUnavailable
	}
	if err = tx.Commit(); err != nil {
		return IdentitySecurityHTTPMutationResultDTO{}, identitySecurityDatabaseError(err)
	}
	committed = true
	return result, nil
}

func configureIdentitySecurityTransaction(
	ctx context.Context,
	tx *sql.Tx,
	store *ProductionIdentityStore,
) error {
	_, err := tx.ExecContext(ctx, `
SELECT set_config('statement_timeout', $1, true),
       set_config('lock_timeout', $2, true)
`, fmt.Sprintf("%dms", store.statementTimeout.Milliseconds()),
		fmt.Sprintf("%dms", store.lockTimeout.Milliseconds()))
	return err
}

func validIdentitySecurityMutation(mutation IdentitySecurityMutation, now time.Time) bool {
	ticket := mutation.Ticket
	if !validPostgresIdentityVerificationUUID(strings.TrimSpace(mutation.AccountID)) ||
		mutation.AccountID != strings.TrimSpace(mutation.ActorID) ||
		ticket.AccountID != mutation.AccountID || ticket.Operation != mutation.Operation ||
		!validIdentitySecurityDigest(strings.TrimSpace(ticket.TicketID)) ||
		!validIdentitySecurityDigest(ticket.ReceiptDigest) ||
		!validIdentitySecurityIdempotencyKey(mutation.IdempotencyKey) ||
		ticket.ExpiresAt.IsZero() {
		return false
	}
	return validIdentitySecurityOperation(mutation.Operation)
}

func validIdentitySecurityOperation(operation string) bool {
	switch operation {
	case "password_enroll", "password_change", "password_recovery", "mfa_enroll", "mfa_confirm":
		return true
	default:
		return false
	}
}

func validIdentitySecurityIdempotencyKey(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) < 8 || len(value) > 255 {
		return false
	}
	for _, character := range value {
		if (character >= 'a' && character <= 'z') ||
			(character >= 'A' && character <= 'Z') ||
			(character >= '0' && character <= '9') ||
			strings.ContainsRune("._:-", character) {
			continue
		}
		return false
	}
	return true
}

func identitySecurityRequestFingerprint(mutation IdentitySecurityMutation) string {
	canonical := strings.Join([]string{
		IdentitySecurityHTTPSchemaVersion,
		strings.TrimSpace(mutation.AccountID),
		strings.TrimSpace(mutation.ActorID),
		strings.TrimSpace(mutation.SessionID),
		strings.TrimSpace(mutation.Operation),
		strings.TrimSpace(mutation.Ticket.TicketID),
		strings.TrimSpace(mutation.Ticket.ReceiptDigest),
	}, "\x00")
	digest := sha256.Sum256([]byte(canonical))
	return hex.EncodeToString(digest[:])
}

func validIdentitySecurityDigest(value string) bool {
	if len(value) != 64 {
		return false
	}
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == 32
}

func decodeIdentitySecurityJSON(raw []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return fmt.Errorf("identity security projection contains trailing content")
	}
	return nil
}

func validIdentitySecurityPosture(posture IdentitySecurityHTTPPostureDTO) bool {
	if posture.PasswordStatus != "absent" && posture.PasswordStatus != "set" {
		return false
	}
	if posture.TwoFactorStatus != "disabled" && posture.TwoFactorStatus != "pending" &&
		posture.TwoFactorStatus != "enabled" {
		return false
	}
	return posture.TwoFactorOptional && posture.TwoFactorRecommended &&
		posture.RecoveryCodesRemaining >= 0 && posture.SecurityVersion >= 0 &&
		posture.ActiveSessions >= 0
}

func validIdentitySecurityMutationResult(
	operation string,
	result IdentitySecurityHTTPMutationResultDTO,
) bool {
	if result.SessionsRevoked < 0 || result.SecurityVersion < 0 ||
		result.RecoveryCodesRemaining < 0 {
		return false
	}
	switch operation {
	case "password_enroll", "password_change", "password_recovery":
		return result.PasswordStatus == "set" && result.ReauthenticationRequired
	case "mfa_enroll":
		return result.TwoFactorStatus == "pending" && result.ConfirmationRequired
	case "mfa_confirm":
		return result.TwoFactorStatus == "enabled" &&
			result.ReauthenticationRequired && result.RecoveryCodesRemaining >= 6
	default:
		return false
	}
}

func identitySecurityDatabaseError(err error) error {
	if err == nil {
		return nil
	}
	var postgresError *pq.Error
	if errors.As(err, &postgresError) {
		if postgresError.Code == "55000" {
			return ErrIdentitySecurityRejected
		}
		switch postgresError.Code.Class() {
		case "08", "40", "53", "54", "55", "57", "58":
			return ErrIdentitySecurityUnavailable
		default:
			return ErrIdentitySecurityRejected
		}
	}
	return ErrIdentitySecurityUnavailable
}
