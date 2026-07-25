package ashrclone

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"
)

const identitySecurityTicketContextSchema = "ashr.identity_security_ticket.v1"

const productionIdentitySecurityIssuerReadinessQuery = `
SELECT
  current_user = 'a1_security_ticket_issuer'
  AND EXISTS (
    SELECT 1
      FROM pg_roles
     WHERE rolname = current_user
       AND NOT rolsuper
       AND NOT rolbypassrls
       AND NOT rolinherit
       AND NOT rolcanlogin
  )
  AND session_user <> current_user
  AND pg_has_role(session_user, current_user, 'MEMBER')
  AND EXISTS (
    SELECT 1
      FROM pg_roles
     WHERE rolname = session_user
       AND NOT rolsuper
       AND NOT rolbypassrls
       AND NOT rolinherit
       AND rolcanlogin
  )
  AND to_regclass('public.identity_security_ticket_issuance') IS NOT NULL
  AND (
    SELECT relrowsecurity AND relforcerowsecurity
      FROM pg_class
     WHERE oid = 'public.identity_security_ticket_issuance'::regclass
  )
  AND has_function_privilege(
    current_user,
    'public.a1_issue_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,integer,timestamp with time zone)',
    'EXECUTE'
  )
  AND has_function_privilege(
    current_user,
    'public.a1_cancel_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text)',
    'EXECUTE'
  )
  AND NOT has_function_privilege(
    current_user,
    'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,timestamp with time zone)',
    'EXECUTE'
  )
  AND NOT has_function_privilege(
    current_user,
    'public.a1_resolve_identity_security_mutation_ticket(text,text,text,uuid,timestamp with time zone)',
    'EXECUTE'
  )
  AND NOT has_function_privilege(
    current_user,
    'public.a1_execute_identity_security_mutation(text,text,text,uuid)',
    'EXECUTE'
  )
  AND NOT has_function_privilege(
    current_user,
    'public.a1_project_account_security(uuid)',
    'EXECUTE'
  )
  AND NOT has_table_privilege(
    current_user,
    'public.identity_security_ticket_issuance',
    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
  )
  AND NOT has_table_privilege(
    current_user,
    'public.identity_security_receipts',
    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
  )
  AND NOT has_table_privilege(
    current_user,
    'public.identity_security_mutation_tickets',
    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
  )
`

type IdentitySecurityTicketIssueRequest struct {
	OrganizationID      string
	ProjectID           string
	AccountID           string
	ActorID             string
	SessionID           string
	SessionDigest       string
	Operation           string
	IdempotencyKey      string
	ContextDigest       string
	SecretRef           string
	SecretDigest        string
	RecoveryBatchDigest string
	RecoveryCodeCount   int
	ExpiresAt           time.Time
}

type IdentitySecurityIssuedTicket struct {
	TicketID      string    `json:"ticket_id"`
	ReceiptID     string    `json:"step_up_receipt_id"`
	ContextDigest string    `json:"context_digest"`
	ExpiresAt     time.Time `json:"expires_at"`
}

type IdentitySecurityTicketIssuer interface {
	IssueIdentitySecurityMutationTicket(
		context.Context,
		IdentitySecurityTicketIssueRequest,
	) (IdentitySecurityIssuedTicket, error)
	CancelIdentitySecurityMutationTicket(
		context.Context,
		IdentitySecurityTicketIssueRequest,
		IdentitySecurityIssuedTicket,
	) error
}

type ProductionIdentitySecurityTicketIssuerOptions struct {
	DB               *sql.DB
	SQLTimeout       time.Duration
	StatementTimeout time.Duration
	LockTimeout      time.Duration
	Now              func() time.Time
}

// ProductionIdentitySecurityTicketIssuer owns a separate issuer-role
// connection pool. It must never share a runtime-role database handle.
type ProductionIdentitySecurityTicketIssuer struct {
	db               *sql.DB
	sqlTimeout       time.Duration
	statementTimeout time.Duration
	lockTimeout      time.Duration
	now              func() time.Time
}

func NewProductionIdentitySecurityTicketIssuer(
	options ProductionIdentitySecurityTicketIssuerOptions,
) (*ProductionIdentitySecurityTicketIssuer, error) {
	if options.DB == nil {
		return nil, errors.New("identity security ticket issuer database is required")
	}
	if options.SQLTimeout <= 0 {
		options.SQLTimeout = 5 * time.Second
	}
	if options.StatementTimeout <= 0 {
		options.StatementTimeout = 3 * time.Second
	}
	if options.LockTimeout <= 0 {
		options.LockTimeout = time.Second
	}
	if options.Now == nil {
		options.Now = time.Now
	}
	if options.SQLTimeout > 30*time.Second ||
		options.StatementTimeout > options.SQLTimeout ||
		options.LockTimeout > options.StatementTimeout {
		return nil, errors.New("identity security ticket issuer timeouts are invalid")
	}
	return &ProductionIdentitySecurityTicketIssuer{
		db: options.DB, sqlTimeout: options.SQLTimeout,
		statementTimeout: options.StatementTimeout,
		lockTimeout:      options.LockTimeout, now: options.Now,
	}, nil
}

func (issuer *ProductionIdentitySecurityTicketIssuer) Ready(ctx context.Context) error {
	if issuer == nil || issuer.db == nil || ctx == nil {
		return ErrIdentitySecurityUnavailable
	}
	readyCtx, cancel := context.WithTimeout(ctx, issuer.sqlTimeout)
	defer cancel()
	var ready bool
	if err := issuer.db.QueryRowContext(
		readyCtx,
		productionIdentitySecurityIssuerReadinessQuery,
	).Scan(&ready); err != nil {
		return identitySecurityDatabaseError(err)
	}
	if !ready {
		return ErrIdentitySecurityUnavailable
	}
	return nil
}

func (issuer *ProductionIdentitySecurityTicketIssuer) IssueIdentitySecurityMutationTicket(
	ctx context.Context,
	request IdentitySecurityTicketIssueRequest,
) (IdentitySecurityIssuedTicket, error) {
	now := issuer.nowUTC()
	request = normalizeIdentitySecurityTicketIssueRequest(request)
	if issuer == nil || issuer.db == nil || ctx == nil ||
		!validIdentitySecurityTicketIssueRequest(request, now) {
		return IdentitySecurityIssuedTicket{}, ErrIdentitySecurityRejected
	}
	expectedContext := identitySecurityTicketContextDigest(request)
	if request.ContextDigest != expectedContext {
		return IdentitySecurityIssuedTicket{}, ErrIdentitySecurityRejected
	}

	queryCtx, cancel := context.WithTimeout(ctx, issuer.sqlTimeout)
	defer cancel()
	tx, err := issuer.db.BeginTx(
		queryCtx,
		&sql.TxOptions{Isolation: sql.LevelReadCommitted},
	)
	if err != nil {
		return IdentitySecurityIssuedTicket{}, identitySecurityDatabaseError(err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if err = issuer.configureTransaction(queryCtx, tx, request); err != nil {
		return IdentitySecurityIssuedTicket{}, identitySecurityDatabaseError(err)
	}
	var raw []byte
	err = tx.QueryRowContext(queryCtx, `
SELECT a1_issue_scoped_identity_security_mutation_ticket(
  $1::uuid,$2::uuid,$3::uuid,$4::uuid,$5::uuid,$6,$7,$8,$9,
  NULLIF($10,''),NULLIF($11,''),NULLIF($12,''),NULLIF($13::integer,0),$14
)
`, request.OrganizationID, request.ProjectID, request.AccountID,
		request.ActorID, request.SessionID, request.SessionDigest,
		request.Operation, request.IdempotencyKey, request.ContextDigest,
		request.SecretRef, request.SecretDigest, request.RecoveryBatchDigest,
		request.RecoveryCodeCount, request.ExpiresAt).Scan(&raw)
	if err != nil {
		return IdentitySecurityIssuedTicket{}, identitySecurityDatabaseError(err)
	}
	var issued IdentitySecurityIssuedTicket
	if len(raw) == 0 || decodeIdentitySecurityJSON(raw, &issued) != nil ||
		issued.ContextDigest != request.ContextDigest ||
		!validIdentitySecurityDigest(issued.TicketID) ||
		!validIdentitySecurityDigest(issued.ReceiptID) ||
		issued.ExpiresAt.IsZero() ||
		!issued.ExpiresAt.After(now) ||
		issued.ExpiresAt.After(request.ExpiresAt) {
		return IdentitySecurityIssuedTicket{}, ErrIdentitySecurityUnavailable
	}
	if err = tx.Commit(); err != nil {
		return IdentitySecurityIssuedTicket{}, identitySecurityDatabaseError(err)
	}
	committed = true
	issued.ExpiresAt = issued.ExpiresAt.UTC()
	return issued, nil
}

func (issuer *ProductionIdentitySecurityTicketIssuer) CancelIdentitySecurityMutationTicket(
	ctx context.Context,
	request IdentitySecurityTicketIssueRequest,
	issued IdentitySecurityIssuedTicket,
) error {
	request = normalizeIdentitySecurityTicketIssueRequest(request)
	issued.TicketID = strings.TrimSpace(issued.TicketID)
	issued.ReceiptID = strings.TrimSpace(issued.ReceiptID)
	issued.ContextDigest = strings.TrimSpace(issued.ContextDigest)
	if issuer == nil || issuer.db == nil || ctx == nil ||
		!validIdentitySecurityTicketIssueRequestShape(request) ||
		request.ContextDigest != identitySecurityTicketContextDigest(request) ||
		issued.ContextDigest != request.ContextDigest ||
		!validIdentitySecurityDigest(issued.TicketID) ||
		!validIdentitySecurityDigest(issued.ReceiptID) {
		return ErrIdentitySecurityRejected
	}
	queryCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), issuer.sqlTimeout)
	defer cancel()
	tx, err := issuer.db.BeginTx(
		queryCtx,
		&sql.TxOptions{Isolation: sql.LevelReadCommitted},
	)
	if err != nil {
		return identitySecurityDatabaseError(err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if err = issuer.configureTransaction(queryCtx, tx, request); err != nil {
		return identitySecurityDatabaseError(err)
	}
	var canceled bool
	err = tx.QueryRowContext(queryCtx, `
SELECT a1_cancel_scoped_identity_security_mutation_ticket(
  $1::uuid,$2::uuid,$3::uuid,$4::uuid,$5::uuid,$6,$7,$8,$9,$10
)
`, request.OrganizationID, request.ProjectID, request.AccountID,
		request.ActorID, request.SessionID, request.Operation,
		request.IdempotencyKey, request.ContextDigest, issued.TicketID,
		issued.ReceiptID).Scan(&canceled)
	if err != nil {
		return identitySecurityDatabaseError(err)
	}
	if !canceled {
		return ErrIdentitySecurityRejected
	}
	if err = tx.Commit(); err != nil {
		return identitySecurityDatabaseError(err)
	}
	committed = true
	return nil
}

func (issuer *ProductionIdentitySecurityTicketIssuer) configureTransaction(
	ctx context.Context,
	tx *sql.Tx,
	request IdentitySecurityTicketIssueRequest,
) error {
	_, err := tx.ExecContext(ctx, `
SELECT set_config('statement_timeout', $1, true),
       set_config('lock_timeout', $2, true),
       set_config('app.a1_organization_id', $3, true),
       set_config('app.a1_project_id', $4, true),
       set_config('app.a1_principal_id', $5, true)
`, fmt.Sprintf("%dms", issuer.statementTimeout.Milliseconds()),
		fmt.Sprintf("%dms", issuer.lockTimeout.Milliseconds()),
		request.OrganizationID, request.ProjectID, request.AccountID)
	return err
}

func (issuer *ProductionIdentitySecurityTicketIssuer) nowUTC() time.Time {
	if issuer == nil || issuer.now == nil {
		return time.Time{}
	}
	return issuer.now().UTC()
}

func normalizeIdentitySecurityTicketIssueRequest(
	request IdentitySecurityTicketIssueRequest,
) IdentitySecurityTicketIssueRequest {
	request.OrganizationID = strings.TrimSpace(request.OrganizationID)
	request.ProjectID = strings.TrimSpace(request.ProjectID)
	request.AccountID = strings.TrimSpace(request.AccountID)
	request.ActorID = strings.TrimSpace(request.ActorID)
	request.SessionID = strings.TrimSpace(request.SessionID)
	request.SessionDigest = strings.TrimSpace(request.SessionDigest)
	request.Operation = strings.TrimSpace(request.Operation)
	request.IdempotencyKey = strings.TrimSpace(request.IdempotencyKey)
	request.ContextDigest = strings.TrimSpace(request.ContextDigest)
	request.SecretRef = strings.TrimSpace(request.SecretRef)
	request.SecretDigest = strings.TrimSpace(request.SecretDigest)
	request.RecoveryBatchDigest = strings.TrimSpace(request.RecoveryBatchDigest)
	request.ExpiresAt = request.ExpiresAt.UTC().Truncate(time.Microsecond)
	return request
}

func validIdentitySecurityTicketIssueRequest(
	request IdentitySecurityTicketIssueRequest,
	now time.Time,
) bool {
	if !validIdentitySecurityTicketIssueRequestShape(request) ||
		now.IsZero() || request.ExpiresAt.IsZero() ||
		!request.ExpiresAt.After(now) ||
		request.ExpiresAt.After(now.Add(5*time.Minute)) {
		return false
	}
	return true
}

func validIdentitySecurityTicketIssueRequestShape(
	request IdentitySecurityTicketIssueRequest,
) bool {
	if !validPostgresIdentityVerificationUUID(request.OrganizationID) ||
		!validPostgresIdentityVerificationUUID(request.ProjectID) ||
		!validPostgresIdentityVerificationUUID(request.AccountID) ||
		request.ActorID != request.AccountID ||
		!validPostgresIdentityVerificationUUID(request.SessionID) ||
		!validIdentitySecurityDigest(request.SessionDigest) ||
		!validIdentitySecurityExecutableOperation(request.Operation) ||
		!validIdentitySecurityIdempotencyKey(request.IdempotencyKey) ||
		!validIdentitySecurityDigest(request.ContextDigest) {
		return false
	}
	switch request.Operation {
	case "password_enroll", "password_change", "password_recovery", "mfa_enroll":
		return identitySecurityProcessorReferencePattern.MatchString(
			request.SecretRef,
		) &&
			validIdentitySecurityDigest(request.SecretDigest) &&
			request.RecoveryBatchDigest == "" &&
			request.RecoveryCodeCount == 0
	case "mfa_confirm":
		return request.SecretRef == "" &&
			request.SecretDigest == "" &&
			validIdentitySecurityDigest(request.RecoveryBatchDigest) &&
			request.RecoveryCodeCount >= 6 &&
			request.RecoveryCodeCount <= 20
	default:
		return false
	}
}

func identitySecurityTicketContextDigest(
	request IdentitySecurityTicketIssueRequest,
) string {
	canonical := strings.Join([]string{
		identitySecurityTicketContextSchema,
		request.OrganizationID,
		request.ProjectID,
		request.AccountID,
		request.ActorID,
		request.SessionID,
		request.SessionDigest,
		request.Operation,
		request.IdempotencyKey,
	}, "\x00")
	digest := sha256.Sum256([]byte(canonical))
	return hex.EncodeToString(digest[:])
}

var _ IdentitySecurityTicketIssuer = (*ProductionIdentitySecurityTicketIssuer)(nil)
