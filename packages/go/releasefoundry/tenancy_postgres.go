package releasefoundry

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/lib/pq"
)

type PostgresTenancyStore struct {
	db               *sql.DB
	sqlTimeout       time.Duration
	statementTimeout time.Duration
	lockTimeout      time.Duration
}

func newPostgresTenancyStore(
	db *sql.DB,
	sqlTimeout time.Duration,
	statementTimeout time.Duration,
	lockTimeout time.Duration,
) (*PostgresTenancyStore, error) {
	if db == nil || sqlTimeout <= 0 || statementTimeout <= 0 ||
		lockTimeout <= 0 || statementTimeout > sqlTimeout ||
		lockTimeout > statementTimeout {
		return nil, fmt.Errorf("PostgreSQL tenancy store configuration is invalid")
	}
	return &PostgresTenancyStore{
		db:               db,
		sqlTimeout:       sqlTimeout,
		statementTimeout: statementTimeout,
		lockTimeout:      lockTimeout,
	}, nil
}

func (store *ProductionIdentityStore) NewPostgresTenancyStore() (*PostgresTenancyStore, error) {
	if store == nil || store.db == nil {
		return nil, fmt.Errorf("production identity store is not configured")
	}
	return newPostgresTenancyStore(
		store.db,
		store.sqlTimeout,
		store.statementTimeout,
		store.lockTimeout,
	)
}

func (store *PostgresTenancyStore) QueryTenancy(
	ctx context.Context,
	query TenancyQuery,
) (TenancyListResult, error) {
	if store == nil || store.db == nil {
		return TenancyListResult{}, ErrTenancyUnavailable
	}
	normalized, err := normalizeTenancyQuery(query)
	if err != nil {
		return TenancyListResult{}, err
	}
	operationCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	tx, err := store.db.BeginTx(
		operationCtx,
		&sql.TxOptions{Isolation: sql.LevelReadCommitted, ReadOnly: true},
	)
	if err != nil {
		return TenancyListResult{}, mapPostgresTenancyError(err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if err := configurePostgresTenancyTransaction(
		operationCtx,
		tx,
		store.statementTimeout,
		store.lockTimeout,
	); err != nil {
		return TenancyListResult{}, mapPostgresTenancyError(err)
	}
	var payload []byte
	err = tx.QueryRowContext(operationCtx, `
SELECT a1_tenancy_query($1::uuid, $2, $3::uuid, $4::uuid)
`,
		normalized.ActorPrincipalID,
		normalized.Operation,
		nullableTenancyUUID(normalized.OrganizationID),
		nullableTenancyUUID(normalized.ProjectID),
	).Scan(&payload)
	if err != nil {
		return TenancyListResult{}, mapPostgresTenancyError(err)
	}
	result, err := parseTenancyListResult(normalized, payload)
	if err != nil {
		return TenancyListResult{}, ErrTenancyUnavailable
	}
	if err := tx.Commit(); err != nil {
		return TenancyListResult{}, mapPostgresTenancyError(err)
	}
	committed = true
	return result, nil
}

func (store *PostgresTenancyStore) MutateTenancy(
	ctx context.Context,
	mutation TenancyMutation,
) (TenancyMutationResult, error) {
	if store == nil || store.db == nil {
		return TenancyMutationResult{}, ErrTenancyUnavailable
	}
	normalized, payloadJSON, err := normalizeTenancyMutation(mutation)
	if err != nil {
		return TenancyMutationResult{}, err
	}
	idempotencyDigest := tenancySHA256(
		"releasefoundry.tenancy.idempotency.v1",
		normalized.ActorPrincipalID,
		normalized.Operation,
		normalized.OrganizationID,
		normalized.IdempotencyKey,
	)
	requestDigest := tenancySHA256(
		"releasefoundry.tenancy.request.v1",
		normalized.ActorPrincipalID,
		normalized.Operation,
		normalized.OrganizationID,
		normalized.ProjectID,
		normalized.EnvironmentID,
		normalized.TargetAccountID,
		string(payloadJSON),
	)
	operationCtx, cancel := context.WithTimeout(ctx, store.sqlTimeout)
	defer cancel()
	tx, err := store.db.BeginTx(
		operationCtx,
		&sql.TxOptions{Isolation: sql.LevelReadCommitted},
	)
	if err != nil {
		return TenancyMutationResult{}, mapPostgresTenancyError(err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()
	if err := configurePostgresTenancyTransaction(
		operationCtx,
		tx,
		store.statementTimeout,
		store.lockTimeout,
	); err != nil {
		return TenancyMutationResult{}, mapPostgresTenancyError(err)
	}
	var resultPayload []byte
	var idempotentReplay bool
	var completedAt time.Time
	err = tx.QueryRowContext(operationCtx, `
SELECT result_payload, idempotent_replay, completed_at
  FROM a1_tenancy_mutate(
    $1::uuid, $2, $3::uuid, $4::uuid, $5::uuid, $6::uuid,
    $7, $8, $9, $10, $11::jsonb
  )
`,
		normalized.ActorPrincipalID,
		normalized.Operation,
		nullableTenancyUUID(normalized.OrganizationID),
		nullableTenancyUUID(normalized.ProjectID),
		nullableTenancyUUID(normalized.EnvironmentID),
		nullableTenancyUUID(normalized.TargetAccountID),
		idempotencyDigest,
		requestDigest,
		normalized.RequestID,
		nullableTenancyText(normalized.TraceID),
		string(payloadJSON),
	).Scan(&resultPayload, &idempotentReplay, &completedAt)
	if err != nil {
		return TenancyMutationResult{}, mapPostgresTenancyError(err)
	}
	publicResult, err := parseTenancyMutationResource(normalized, resultPayload)
	if err != nil || completedAt.IsZero() {
		return TenancyMutationResult{}, ErrTenancyUnavailable
	}
	if err := tx.Commit(); err != nil {
		return TenancyMutationResult{}, mapPostgresTenancyError(err)
	}
	committed = true
	return TenancyMutationResult{
		Result:           publicResult,
		IdempotentReplay: idempotentReplay,
		CompletedAt:      completedAt.UTC(),
	}, nil
}

func configurePostgresTenancyTransaction(
	ctx context.Context,
	tx *sql.Tx,
	statementTimeout time.Duration,
	lockTimeout time.Duration,
) error {
	if tx == nil {
		return ErrTenancyUnavailable
	}
	_, err := tx.ExecContext(ctx, `
SELECT set_config('statement_timeout', $1, true),
       set_config('lock_timeout', $2, true)
`,
		fmt.Sprintf("%dms", statementTimeout.Milliseconds()),
		fmt.Sprintf("%dms", lockTimeout.Milliseconds()),
	)
	return err
}

func normalizeTenancyQuery(query TenancyQuery) (TenancyQuery, error) {
	query.ActorPrincipalID = strings.TrimSpace(query.ActorPrincipalID)
	query.Operation = strings.TrimSpace(query.Operation)
	query.OrganizationID = strings.TrimSpace(query.OrganizationID)
	query.ProjectID = strings.TrimSpace(query.ProjectID)
	if !validPostgresIdentityVerificationUUID(query.ActorPrincipalID) ||
		!validTenancyQueryOperation(query.Operation) {
		return TenancyQuery{}, ErrTenancyInvalidRequest
	}
	switch query.Operation {
	case TenancyOperationOrganizationList:
		if query.OrganizationID != "" || query.ProjectID != "" {
			return TenancyQuery{}, ErrTenancyInvalidRequest
		}
	case TenancyOperationProjectList:
		if !validPostgresIdentityVerificationUUID(query.OrganizationID) ||
			query.ProjectID != "" {
			return TenancyQuery{}, ErrTenancyInvalidRequest
		}
	case TenancyOperationEnvironmentList, TenancyOperationProjectMembershipList:
		if !validPostgresIdentityVerificationUUID(query.OrganizationID) ||
			!validPostgresIdentityVerificationUUID(query.ProjectID) {
			return TenancyQuery{}, ErrTenancyInvalidRequest
		}
	}
	return query, nil
}

func normalizeTenancyMutation(
	mutation TenancyMutation,
) (TenancyMutation, []byte, error) {
	mutation.ActorPrincipalID = strings.TrimSpace(mutation.ActorPrincipalID)
	mutation.Operation = strings.TrimSpace(mutation.Operation)
	mutation.OrganizationID = strings.TrimSpace(mutation.OrganizationID)
	mutation.ProjectID = strings.TrimSpace(mutation.ProjectID)
	mutation.EnvironmentID = strings.TrimSpace(mutation.EnvironmentID)
	mutation.TargetAccountID = strings.TrimSpace(mutation.TargetAccountID)
	mutation.IdempotencyKey = strings.TrimSpace(mutation.IdempotencyKey)
	mutation.RequestID = strings.TrimSpace(mutation.RequestID)
	mutation.TraceID = strings.TrimSpace(mutation.TraceID)
	if !validPostgresIdentityVerificationUUID(mutation.ActorPrincipalID) ||
		!validTenancyMutationOperation(mutation.Operation) ||
		!validTenancyCorrelationID(mutation.RequestID) ||
		(mutation.TraceID != "" && !validTenancyCorrelationID(mutation.TraceID)) {
		return TenancyMutation{}, nil, ErrTenancyInvalidRequest
	}
	if !validTenancyIdempotencyKey(mutation.IdempotencyKey) {
		return TenancyMutation{}, nil, ErrTenancyInvalidIdempotencyKey
	}
	payload, err := normalizeTenancyMutationPayload(mutation.Operation, mutation.Payload)
	if err != nil {
		return TenancyMutation{}, nil, err
	}
	if err := validateTenancyMutationScope(mutation); err != nil {
		return TenancyMutation{}, nil, err
	}
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return TenancyMutation{}, nil, ErrTenancyInvalidRequest
	}
	mutation.Payload = payload
	return mutation, payloadJSON, nil
}

func validateTenancyMutationScope(mutation TenancyMutation) error {
	validOrganization := mutation.OrganizationID == "" ||
		validPostgresIdentityVerificationUUID(mutation.OrganizationID)
	validProject := mutation.ProjectID == "" ||
		validPostgresIdentityVerificationUUID(mutation.ProjectID)
	validEnvironment := mutation.EnvironmentID == "" ||
		validPostgresIdentityVerificationUUID(mutation.EnvironmentID)
	validTarget := mutation.TargetAccountID == "" ||
		validPostgresIdentityVerificationUUID(mutation.TargetAccountID)
	if !validOrganization || !validProject || !validEnvironment || !validTarget {
		return ErrTenancyInvalidRequest
	}
	switch mutation.Operation {
	case TenancyOperationOrganizationCreate:
		if mutation.OrganizationID != "" || mutation.ProjectID != "" ||
			mutation.EnvironmentID != "" || mutation.TargetAccountID != "" {
			return ErrTenancyInvalidRequest
		}
	case TenancyOperationProjectCreate:
		if mutation.OrganizationID == "" || mutation.ProjectID != "" ||
			mutation.EnvironmentID != "" || mutation.TargetAccountID != "" {
			return ErrTenancyInvalidRequest
		}
	case TenancyOperationProjectUpdate, TenancyOperationProjectArchive,
		TenancyOperationProjectRestore:
		if mutation.OrganizationID == "" || mutation.ProjectID == "" ||
			mutation.EnvironmentID != "" || mutation.TargetAccountID != "" {
			return ErrTenancyInvalidRequest
		}
	case TenancyOperationEnvironmentCreate:
		if mutation.OrganizationID == "" || mutation.ProjectID == "" ||
			mutation.EnvironmentID != "" || mutation.TargetAccountID != "" {
			return ErrTenancyInvalidRequest
		}
	case TenancyOperationEnvironmentDisable, TenancyOperationEnvironmentEnable:
		if mutation.OrganizationID == "" || mutation.ProjectID == "" ||
			mutation.EnvironmentID == "" || mutation.TargetAccountID != "" {
			return ErrTenancyInvalidRequest
		}
	case TenancyOperationProjectMembershipSet,
		TenancyOperationProjectMembershipRevoke:
		if mutation.OrganizationID == "" || mutation.ProjectID == "" ||
			mutation.EnvironmentID != "" || mutation.TargetAccountID == "" {
			return ErrTenancyInvalidRequest
		}
	default:
		return ErrTenancyInvalidRequest
	}
	return nil
}

func normalizeTenancyMutationPayload(
	operation string,
	input map[string]any,
) (map[string]any, error) {
	if input == nil {
		input = map[string]any{}
	}
	output := make(map[string]any, len(input))
	stringField := func(name string, required bool, lower bool) (string, error) {
		raw, exists := input[name]
		if !exists {
			if required {
				return "", ErrTenancyInvalidRequest
			}
			return "", nil
		}
		value, ok := raw.(string)
		if !ok {
			return "", ErrTenancyInvalidRequest
		}
		value = strings.TrimSpace(value)
		if lower {
			value = strings.ToLower(value)
		}
		if value == "" {
			return "", ErrTenancyInvalidRequest
		}
		output[name] = value
		return value, nil
	}
	requireOnly := func(names ...string) error {
		allowed := make(map[string]struct{}, len(names))
		for _, name := range names {
			allowed[name] = struct{}{}
		}
		for name := range input {
			if _, ok := allowed[name]; !ok {
				return ErrTenancyInvalidRequest
			}
		}
		return nil
	}
	switch operation {
	case TenancyOperationOrganizationCreate, TenancyOperationProjectCreate:
		if err := requireOnly("slug", "display_name"); err != nil {
			return nil, err
		}
		slug, err := stringField("slug", true, true)
		if err != nil || !validTenancySlug(slug) {
			return nil, ErrTenancyInvalidRequest
		}
		displayName, err := stringField("display_name", true, false)
		if err != nil || len(displayName) > 120 {
			return nil, ErrTenancyInvalidRequest
		}
	case TenancyOperationProjectUpdate:
		if err := requireOnly("slug", "display_name"); err != nil || len(input) == 0 {
			return nil, ErrTenancyInvalidRequest
		}
		if _, exists := input["slug"]; exists {
			slug, err := stringField("slug", false, true)
			if err != nil || !validTenancySlug(slug) {
				return nil, ErrTenancyInvalidRequest
			}
		}
		if _, exists := input["display_name"]; exists {
			displayName, err := stringField("display_name", false, false)
			if err != nil || len(displayName) > 120 {
				return nil, ErrTenancyInvalidRequest
			}
		}
	case TenancyOperationEnvironmentCreate:
		if err := requireOnly("name", "kind"); err != nil {
			return nil, err
		}
		name, err := stringField("name", true, true)
		if err != nil || !validTenancyEnvironmentName(name) {
			return nil, ErrTenancyInvalidRequest
		}
		kind, err := stringField("kind", true, true)
		if err != nil || !validTenancyEnvironmentKind(kind) {
			return nil, ErrTenancyInvalidRequest
		}
	case TenancyOperationProjectMembershipSet:
		if err := requireOnly("role"); err != nil {
			return nil, err
		}
		role, err := stringField("role", true, true)
		if err != nil || !validTenancyWritableProjectRole(role) {
			return nil, ErrTenancyInvalidRequest
		}
	case TenancyOperationProjectArchive, TenancyOperationProjectRestore,
		TenancyOperationEnvironmentDisable, TenancyOperationEnvironmentEnable,
		TenancyOperationProjectMembershipRevoke:
		if len(input) != 0 {
			return nil, ErrTenancyInvalidRequest
		}
	default:
		return nil, ErrTenancyInvalidRequest
	}
	return output, nil
}

func parseTenancyListResult(
	query TenancyQuery,
	payload []byte,
) (TenancyListResult, error) {
	var envelope struct {
		SchemaVersion string            `json:"schema_version"`
		Items         []json.RawMessage `json:"items"`
		Count         int               `json:"count"`
	}
	if err := strictUnmarshalTenancyJSON(payload, &envelope); err != nil ||
		envelope.SchemaVersion != TenancySchemaVersion ||
		envelope.Count < 0 || envelope.Count != len(envelope.Items) {
		return TenancyListResult{}, ErrTenancyUnavailable
	}
	switch query.Operation {
	case TenancyOperationOrganizationList:
		items := make([]TenancyOrganization, 0, len(envelope.Items))
		for _, raw := range envelope.Items {
			var item TenancyOrganization
			if err := strictUnmarshalTenancyJSON(raw, &item); err != nil ||
				validateTenancyScopedResource(item, "", "", "", "") != nil {
				return TenancyListResult{}, ErrTenancyUnavailable
			}
			items = append(items, item)
		}
		return TenancyListResult{TenancySchemaVersion, items, len(items)}, nil
	case TenancyOperationProjectList:
		items := make([]TenancyProject, 0, len(envelope.Items))
		for _, raw := range envelope.Items {
			var item TenancyProject
			if err := strictUnmarshalTenancyJSON(raw, &item); err != nil ||
				validateTenancyScopedResource(
					item, query.OrganizationID, "", "", "",
				) != nil {
				return TenancyListResult{}, ErrTenancyUnavailable
			}
			items = append(items, item)
		}
		return TenancyListResult{TenancySchemaVersion, items, len(items)}, nil
	case TenancyOperationEnvironmentList:
		items := make([]TenancyEnvironment, 0, len(envelope.Items))
		for _, raw := range envelope.Items {
			var item TenancyEnvironment
			if err := strictUnmarshalTenancyJSON(raw, &item); err != nil ||
				validateTenancyScopedResource(
					item, query.OrganizationID, query.ProjectID, "", "",
				) != nil {
				return TenancyListResult{}, ErrTenancyUnavailable
			}
			items = append(items, item)
		}
		return TenancyListResult{TenancySchemaVersion, items, len(items)}, nil
	case TenancyOperationProjectMembershipList:
		items := make([]TenancyProjectMembership, 0, len(envelope.Items))
		for _, raw := range envelope.Items {
			var item TenancyProjectMembership
			if err := strictUnmarshalTenancyJSON(raw, &item); err != nil ||
				validateTenancyScopedResource(
					item, query.OrganizationID, query.ProjectID, "", "",
				) != nil {
				return TenancyListResult{}, ErrTenancyUnavailable
			}
			items = append(items, item)
		}
		return TenancyListResult{TenancySchemaVersion, items, len(items)}, nil
	default:
		return TenancyListResult{}, ErrTenancyUnavailable
	}
}

func parseTenancyMutationResource(
	mutation TenancyMutation,
	payload []byte,
) (any, error) {
	var result any
	switch mutation.Operation {
	case TenancyOperationOrganizationCreate:
		var item TenancyOrganization
		if err := strictUnmarshalTenancyJSON(payload, &item); err != nil {
			return nil, err
		}
		result = item
	case TenancyOperationProjectCreate, TenancyOperationProjectUpdate,
		TenancyOperationProjectArchive, TenancyOperationProjectRestore:
		var item TenancyProject
		if err := strictUnmarshalTenancyJSON(payload, &item); err != nil {
			return nil, err
		}
		result = item
	case TenancyOperationEnvironmentCreate, TenancyOperationEnvironmentDisable,
		TenancyOperationEnvironmentEnable:
		var item TenancyEnvironment
		if err := strictUnmarshalTenancyJSON(payload, &item); err != nil {
			return nil, err
		}
		result = item
	case TenancyOperationProjectMembershipSet,
		TenancyOperationProjectMembershipRevoke:
		var item TenancyProjectMembership
		if err := strictUnmarshalTenancyJSON(payload, &item); err != nil {
			return nil, err
		}
		result = item
	default:
		return nil, ErrTenancyUnavailable
	}
	if err := validateTenancyScopedResource(
		result,
		mutation.OrganizationID,
		mutation.ProjectID,
		mutation.EnvironmentID,
		mutation.TargetAccountID,
	); err != nil {
		return nil, err
	}
	return result, nil
}

func tenancySHA256(domain string, components ...string) string {
	digest := sha256.New()
	writeDigestComponent := func(value string) {
		var size [8]byte
		binary.BigEndian.PutUint64(size[:], uint64(len(value)))
		_, _ = digest.Write(size[:])
		_, _ = digest.Write([]byte(value))
	}
	writeDigestComponent(domain)
	for _, component := range components {
		writeDigestComponent(component)
	}
	return hex.EncodeToString(digest.Sum(nil))
}

func nullableTenancyUUID(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func nullableTenancyText(value string) any {
	if value == "" {
		return nil
	}
	return value
}

func validTenancyIdempotencyKey(value string) bool {
	if len(value) < 8 || len(value) > 128 ||
		value != strings.TrimSpace(value) {
		return false
	}
	for index := 0; index < len(value); index++ {
		character := value[index]
		if (character >= 'A' && character <= 'Z') ||
			(character >= 'a' && character <= 'z') ||
			(character >= '0' && character <= '9') ||
			(index > 0 && (character == '.' || character == '_' ||
				character == ':' || character == '-')) {
			continue
		}
		return false
	}
	return true
}

func validTenancyCorrelationID(value string) bool {
	if len(value) < 1 || len(value) > 128 ||
		value != strings.TrimSpace(value) {
		return false
	}
	for index := 0; index < len(value); index++ {
		character := value[index]
		if (character >= 'A' && character <= 'Z') ||
			(character >= 'a' && character <= 'z') ||
			(character >= '0' && character <= '9') ||
			(index > 0 && (character == '.' || character == '_' ||
				character == ':' || character == '/' || character == '-')) {
			continue
		}
		return false
	}
	return true
}

func mapPostgresTenancyError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return ErrTenancyUnavailable
	}
	for _, domain := range []error{
		ErrTenancyAuthenticationRequired,
		ErrTenancyInvalidRequest,
		ErrTenancyInvalidIdempotencyKey,
		ErrTenancyIdempotencyConflict,
		ErrTenancyForbidden,
		ErrTenancyNotFound,
		ErrTenancyStateConflict,
		ErrTenancyLastOwner,
		ErrTenancyUnavailable,
	} {
		if errors.Is(err, domain) {
			return domain
		}
	}
	var postgresError *pq.Error
	if !errors.As(err, &postgresError) {
		return ErrTenancyUnavailable
	}
	switch strings.TrimSpace(postgresError.Message) {
	case "tenancy_authentication_required":
		return ErrTenancyAuthenticationRequired
	case "tenancy_invalid_request":
		return ErrTenancyInvalidRequest
	case "tenancy_idempotency_conflict":
		return ErrTenancyIdempotencyConflict
	case "tenancy_forbidden":
		return ErrTenancyForbidden
	case "tenancy_not_found":
		return ErrTenancyNotFound
	case "tenancy_state_conflict":
		return ErrTenancyStateConflict
	case "tenancy_last_owner":
		return ErrTenancyLastOwner
	}
	switch string(postgresError.Code) {
	case "22023":
		return ErrTenancyInvalidRequest
	case "42501":
		return ErrTenancyForbidden
	case "P0002":
		return ErrTenancyNotFound
	case "P0003":
		return ErrTenancyLastOwner
	case "23505", "55000":
		return ErrTenancyStateConflict
	case "40001", "40P01", "55P03", "57014":
		return ErrTenancyUnavailable
	default:
		if strings.HasPrefix(string(postgresError.Code), "08") {
			return ErrTenancyUnavailable
		}
		return ErrTenancyUnavailable
	}
}

var _ TenancyHTTPStore = (*PostgresTenancyStore)(nil)
