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
  AND to_regclass('public.identity_account_security') IS NOT NULL
  AND to_regclass('public.identity_security_receipts') IS NOT NULL
  AND to_regclass('public.identity_security_mutation_tickets') IS NOT NULL
  AND to_regclass(
    'public.identity_security_mutation_idempotency'
  ) IS NOT NULL
  AND to_regclass('public.identity_security_ticket_issuance') IS NOT NULL
  AND (
    SELECT count(*) = 5
      FROM pg_catalog.pg_class relation
      JOIN pg_catalog.pg_namespace namespace
        ON namespace.oid = relation.relnamespace
     WHERE namespace.nspname = 'public'
       AND relation.relname IN (
         'identity_account_security',
         'identity_security_receipts',
         'identity_security_mutation_tickets',
         'identity_security_mutation_idempotency',
         'identity_security_ticket_issuance'
       )
       AND relation.relrowsecurity
       AND relation.relforcerowsecurity
  )
  AND (
    SELECT count(*) = 5
      AND count(*) FILTER (
        WHERE policy.policyname = policy.tablename || '_self'
          AND policy.permissive = 'PERMISSIVE'
          AND policy.roles = ARRAY['public'::name]
      ) = 5
      FROM pg_catalog.pg_policies policy
     WHERE policy.schemaname = 'public'
       AND policy.tablename IN (
         'identity_account_security',
         'identity_security_receipts',
         'identity_security_mutation_tickets',
         'identity_security_mutation_idempotency',
         'identity_security_ticket_issuance'
       )
  )
  AND to_regprocedure(
    'public.a1_issue_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,integer,text,integer,timestamp with time zone)'
  ) IS NOT NULL
  AND to_regprocedure(
    'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,text,integer,timestamp with time zone)'
  ) IS NOT NULL
  AND to_regprocedure(
    'public.a1_project_identity_security_processor_state(uuid)'
  ) IS NOT NULL
  AND to_regprocedure(
    'public.a1_project_identity_security_mutation_replay(uuid,text,text)'
  ) IS NOT NULL
  AND to_regprocedure(
    'public.a1_issue_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,integer,timestamp with time zone)'
  ) IS NULL
  AND to_regprocedure(
    'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,timestamp with time zone)'
  ) IS NULL
  AND has_schema_privilege(current_user, 'public', 'USAGE')
  AND NOT has_schema_privilege(current_user, 'public', 'CREATE')
  AND NOT has_schema_privilege('public', 'public', 'CREATE')
  AND has_function_privilege(
    current_user,
    'public.a1_issue_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,integer,text,integer,timestamp with time zone)',
    'EXECUTE'
  )
  AND has_function_privilege(
    current_user,
    'public.a1_cancel_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text)',
    'EXECUTE'
  )
  AND NOT has_function_privilege(
    current_user,
    'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,text,integer,timestamp with time zone)',
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
  AND NOT has_function_privilege(
    current_user,
    'public.a1_project_identity_security_processor_state(uuid)',
    'EXECUTE'
  )
  AND NOT has_function_privilege(
    current_user,
    'public.a1_project_identity_security_mutation_replay(uuid,text,text)',
    'EXECUTE'
  )
  AND NOT has_function_privilege(
    current_user,
    'public.a1_mutate_totp_recovery_lifecycle(uuid,text,text,text,text,integer,text,integer,text,text,uuid,text,timestamp with time zone)',
    'EXECUTE'
  )
  AND NOT EXISTS (
    SELECT 1
      FROM unnest(ARRAY[
        'public.identity_account_security'::regclass,
        'public.identity_security_receipts'::regclass,
        'public.identity_security_mutation_tickets'::regclass,
        'public.identity_security_mutation_idempotency'::regclass,
        'public.identity_security_ticket_issuance'::regclass
      ]) AS security_table(table_oid)
     WHERE has_table_privilege(
             current_user,
             security_table.table_oid,
             'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
           )
        OR has_any_column_privilege(
             current_user,
             security_table.table_oid,
             'SELECT,INSERT,UPDATE,REFERENCES'
           )
        OR has_table_privilege(
             'public',
             security_table.table_oid,
             'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
           )
        OR has_any_column_privilege(
             'public',
             security_table.table_oid,
             'SELECT,INSERT,UPDATE,REFERENCES'
           )
  )
  AND NOT EXISTS (
    SELECT 1
      FROM unnest(ARRAY[
        to_regprocedure(
          'public.a1_issue_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,integer,text,integer,timestamp with time zone)'
        ),
        to_regprocedure(
          'public.a1_cancel_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text)'
        ),
        to_regprocedure(
          'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,text,integer,timestamp with time zone)'
        ),
        to_regprocedure(
          'public.a1_project_identity_security_processor_state(uuid)'
        ),
        to_regprocedure(
          'public.a1_project_identity_security_mutation_replay(uuid,text,text)'
        ),
        to_regprocedure(
          'public.a1_mutate_totp_recovery_lifecycle(uuid,text,text,text,text,integer,text,integer,text,text,uuid,text,timestamp with time zone)'
        )
      ]) function_oid
     WHERE function_oid IS NULL
        OR has_function_privilege('public', function_oid, 'EXECUTE')
  )
  AND (
    SELECT count(*) = 6
      FROM pg_catalog.pg_proc function_row
     WHERE function_row.oid IN (
       to_regprocedure(
         'public.a1_issue_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,integer,text,integer,timestamp with time zone)'
       ),
       to_regprocedure(
         'public.a1_cancel_scoped_identity_security_mutation_ticket(uuid,uuid,uuid,uuid,uuid,text,text,text,text,text)'
       ),
       to_regprocedure(
         'public.a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,text,integer,timestamp with time zone)'
       ),
       to_regprocedure(
         'public.a1_project_identity_security_processor_state(uuid)'
       ),
       to_regprocedure(
         'public.a1_project_identity_security_mutation_replay(uuid,text,text)'
       ),
       to_regprocedure(
         'public.a1_mutate_totp_recovery_lifecycle(uuid,text,text,text,text,integer,text,integer,text,text,uuid,text,timestamp with time zone)'
       )
     )
       AND function_row.prosecdef
       AND pg_catalog.pg_get_userbyid(function_row.proowner) <> current_user
       AND NOT pg_catalog.pg_has_role(
         current_user,
         function_row.proowner,
         'MEMBER'
       )
       AND EXISTS (
         SELECT 1
           FROM unnest(
             COALESCE(function_row.proconfig, ARRAY[]::text[])
           ) setting
          WHERE regexp_replace(setting, '\s', '', 'g') =
            'search_path=pg_catalog,public,pg_temp'
       )
  )
`

type IdentitySecurityTicketIssueRequest struct {
	OrganizationID              string
	ProjectID                   string
	AccountID                   string
	ActorID                     string
	SessionID                   string
	SessionDigest               string
	Operation                   string
	IdempotencyKey              string
	ContextDigest               string
	SecretRef                   string
	SecretDigest                string
	ExpectedRecoveryBatchDigest string
	ExpectedRecoveryCodeCount   int
	RecoveryBatchDigest         string
	RecoveryCodeCount           int
	ExpiresAt                   time.Time
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
  NULLIF($10,''),NULLIF($11,''),NULLIF($12,''),$13::integer,
  NULLIF($14,''),$15::integer,$16
)
`, request.OrganizationID, request.ProjectID, request.AccountID,
		request.ActorID, request.SessionID, request.SessionDigest,
		request.Operation, request.IdempotencyKey, request.ContextDigest,
		request.SecretRef, request.SecretDigest,
		request.ExpectedRecoveryBatchDigest,
		request.ExpectedRecoveryCodeCount,
		request.RecoveryBatchDigest,
		request.RecoveryCodeCount,
		request.ExpiresAt).Scan(&raw)
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
	request.ExpectedRecoveryBatchDigest = strings.TrimSpace(
		request.ExpectedRecoveryBatchDigest,
	)
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
			request.ExpectedRecoveryBatchDigest == "" &&
			request.ExpectedRecoveryCodeCount == 0 &&
			request.RecoveryBatchDigest == "" &&
			request.RecoveryCodeCount == 0
	case "mfa_confirm":
		return request.SecretRef == "" &&
			request.SecretDigest == "" &&
			request.ExpectedRecoveryBatchDigest == "" &&
			request.ExpectedRecoveryCodeCount == 0 &&
			validIdentitySecurityDigest(request.RecoveryBatchDigest) &&
			request.RecoveryCodeCount >= 6 &&
			request.RecoveryCodeCount <= 20
	case "mfa_recovery_consume":
		return identitySecurityProcessorReferencePattern.MatchString(
			request.SecretRef,
		) &&
			validIdentitySecurityDigest(request.SecretDigest) &&
			validIdentitySecurityDigest(
				request.ExpectedRecoveryBatchDigest,
			) &&
			request.ExpectedRecoveryCodeCount > 0 &&
			request.ExpectedRecoveryCodeCount <= 20 &&
			validIdentitySecurityDigest(request.RecoveryBatchDigest) &&
			request.RecoveryCodeCount ==
				request.ExpectedRecoveryCodeCount-1
	case "mfa_recovery_rotate":
		return identitySecurityProcessorReferencePattern.MatchString(
			request.SecretRef,
		) &&
			validIdentitySecurityDigest(request.SecretDigest) &&
			validIdentitySecurityDigest(
				request.ExpectedRecoveryBatchDigest,
			) &&
			request.ExpectedRecoveryCodeCount >= 0 &&
			request.ExpectedRecoveryCodeCount <= 20 &&
			validIdentitySecurityDigest(request.RecoveryBatchDigest) &&
			request.RecoveryCodeCount >= 6 &&
			request.RecoveryCodeCount <= 20
	case "mfa_disable":
		return identitySecurityProcessorReferencePattern.MatchString(
			request.SecretRef,
		) &&
			validIdentitySecurityDigest(request.SecretDigest) &&
			validIdentitySecurityDigest(
				request.ExpectedRecoveryBatchDigest,
			) &&
			request.ExpectedRecoveryCodeCount >= 0 &&
			request.ExpectedRecoveryCodeCount <= 20 &&
			request.RecoveryBatchDigest == "" &&
			request.RecoveryCodeCount == 0
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
