package releasefoundry

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"
)

const TenancySchemaVersion = "releasefoundry.tenancy.v1"

const (
	TenancyOperationOrganizationCreate      = "organization.create"
	TenancyOperationOrganizationList        = "organization.list"
	TenancyOperationProjectCreate           = "project.create"
	TenancyOperationProjectList             = "project.list"
	TenancyOperationProjectUpdate           = "project.update"
	TenancyOperationProjectArchive          = "project.archive"
	TenancyOperationProjectRestore          = "project.restore"
	TenancyOperationEnvironmentCreate       = "environment.create"
	TenancyOperationEnvironmentList         = "environment.list"
	TenancyOperationEnvironmentDisable      = "environment.disable"
	TenancyOperationEnvironmentEnable       = "environment.enable"
	TenancyOperationProjectMembershipList   = "project_membership.list"
	TenancyOperationProjectMembershipSet    = "project_membership.set"
	TenancyOperationProjectMembershipRevoke = "project_membership.revoke"
)

var (
	ErrTenancyAuthenticationRequired = errors.New("tenancy authentication required")
	ErrTenancyInvalidRequest         = errors.New("tenancy request is invalid")
	ErrTenancyInvalidIdempotencyKey  = errors.New("tenancy idempotency key is invalid")
	ErrTenancyIdempotencyConflict    = errors.New("tenancy idempotency conflict")
	ErrTenancyForbidden              = errors.New("tenancy operation is forbidden")
	ErrTenancyNotFound               = errors.New("tenancy resource was not found")
	ErrTenancyStateConflict          = errors.New("tenancy lifecycle state conflicts with the operation")
	ErrTenancyLastOwner              = errors.New("tenancy project must retain an active owner")
	ErrTenancyUnavailable            = errors.New("tenancy service is unavailable")
)

type TenancyHTTPStore interface {
	QueryTenancy(context.Context, TenancyQuery) (TenancyListResult, error)
	MutateTenancy(context.Context, TenancyMutation) (TenancyMutationResult, error)
}

type TenancyQuery struct {
	ActorPrincipalID string
	Operation        string
	OrganizationID   string
	ProjectID        string
}

type TenancyMutation struct {
	ActorPrincipalID string
	Operation        string
	OrganizationID   string
	ProjectID        string
	EnvironmentID    string
	TargetAccountID  string
	IdempotencyKey   string
	RequestID        string
	TraceID          string
	Payload          map[string]any
}

type TenancyListResult struct {
	SchemaVersion string `json:"schema_version"`
	Items         any    `json:"items"`
	Count         int    `json:"count"`
}

type TenancyMutationResult struct {
	Result           any
	IdempotentReplay bool
	CompletedAt      time.Time
}

type TenancyMutationEnvelope struct {
	SchemaVersion    string `json:"schema_version"`
	Result           any    `json:"result"`
	RequestID        string `json:"request_id"`
	IdempotentReplay bool   `json:"idempotent_replay"`
}

type TenancyOrganization struct {
	SchemaVersion  string    `json:"schema_version"`
	OrganizationID string    `json:"organization_id"`
	Slug           string    `json:"slug"`
	DisplayName    string    `json:"display_name"`
	Status         string    `json:"status"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}

type TenancyProject struct {
	SchemaVersion  string     `json:"schema_version"`
	OrganizationID string     `json:"organization_id"`
	ProjectID      string     `json:"project_id"`
	Slug           string     `json:"slug"`
	DisplayName    string     `json:"display_name"`
	Status         string     `json:"status"`
	CreatedAt      time.Time  `json:"created_at"`
	UpdatedAt      time.Time  `json:"updated_at"`
	ArchivedAt     *time.Time `json:"archived_at"`
}

type TenancyEnvironment struct {
	SchemaVersion  string     `json:"schema_version"`
	OrganizationID string     `json:"organization_id"`
	ProjectID      string     `json:"project_id"`
	EnvironmentID  string     `json:"environment_id"`
	Name           string     `json:"name"`
	Kind           string     `json:"kind"`
	Status         string     `json:"status"`
	CreatedAt      time.Time  `json:"created_at"`
	UpdatedAt      time.Time  `json:"updated_at"`
	DisabledAt     *time.Time `json:"disabled_at"`
}

type TenancyProjectMembership struct {
	SchemaVersion  string     `json:"schema_version"`
	OrganizationID string     `json:"organization_id"`
	ProjectID      string     `json:"project_id"`
	AccountID      string     `json:"account_id"`
	Role           string     `json:"role"`
	Status         string     `json:"status"`
	CreatedAt      time.Time  `json:"created_at"`
	UpdatedAt      time.Time  `json:"updated_at"`
	ActivatedAt    *time.Time `json:"activated_at"`
	RevokedAt      *time.Time `json:"revoked_at"`
}

func validateTenancyOrganization(value TenancyOrganization) error {
	if value.SchemaVersion != TenancySchemaVersion ||
		!validPostgresIdentityVerificationUUID(value.OrganizationID) ||
		!validTenancySlug(value.Slug) ||
		strings.TrimSpace(value.DisplayName) != value.DisplayName ||
		len(value.DisplayName) < 1 || len(value.DisplayName) > 120 ||
		value.Status != "active" ||
		value.CreatedAt.IsZero() || value.UpdatedAt.IsZero() ||
		value.UpdatedAt.Before(value.CreatedAt) {
		return ErrTenancyUnavailable
	}
	return nil
}

func validateTenancyProject(value TenancyProject) error {
	if value.SchemaVersion != TenancySchemaVersion ||
		!validPostgresIdentityVerificationUUID(value.OrganizationID) ||
		!validPostgresIdentityVerificationUUID(value.ProjectID) ||
		!validTenancySlug(value.Slug) ||
		strings.TrimSpace(value.DisplayName) != value.DisplayName ||
		len(value.DisplayName) < 1 || len(value.DisplayName) > 120 ||
		(value.Status != "active" && value.Status != "archived") ||
		value.CreatedAt.IsZero() || value.UpdatedAt.IsZero() ||
		value.UpdatedAt.Before(value.CreatedAt) {
		return ErrTenancyUnavailable
	}
	if (value.Status == "archived") != (value.ArchivedAt != nil) {
		return ErrTenancyUnavailable
	}
	return nil
}

func validateTenancyEnvironment(value TenancyEnvironment) error {
	if value.SchemaVersion != TenancySchemaVersion ||
		!validPostgresIdentityVerificationUUID(value.OrganizationID) ||
		!validPostgresIdentityVerificationUUID(value.ProjectID) ||
		!validPostgresIdentityVerificationUUID(value.EnvironmentID) ||
		!validTenancyEnvironmentName(value.Name) ||
		!validTenancyEnvironmentKind(value.Kind) ||
		(value.Status != "active" && value.Status != "disabled") ||
		value.CreatedAt.IsZero() || value.UpdatedAt.IsZero() ||
		value.UpdatedAt.Before(value.CreatedAt) {
		return ErrTenancyUnavailable
	}
	if (value.Status == "disabled") != (value.DisabledAt != nil) {
		return ErrTenancyUnavailable
	}
	return nil
}

func validateTenancyProjectMembership(value TenancyProjectMembership) error {
	if value.SchemaVersion != TenancySchemaVersion ||
		!validPostgresIdentityVerificationUUID(value.OrganizationID) ||
		!validPostgresIdentityVerificationUUID(value.ProjectID) ||
		!validPostgresIdentityVerificationUUID(value.AccountID) ||
		!validTenancyReadableProjectRole(value.Role) ||
		(value.Status != "invited" && value.Status != "active" &&
			value.Status != "suspended" && value.Status != "revoked") ||
		value.CreatedAt.IsZero() || value.UpdatedAt.IsZero() ||
		value.UpdatedAt.Before(value.CreatedAt) {
		return ErrTenancyUnavailable
	}
	if value.Status == "active" && value.ActivatedAt == nil {
		return ErrTenancyUnavailable
	}
	if (value.Status == "revoked") != (value.RevokedAt != nil) {
		return ErrTenancyUnavailable
	}
	return nil
}

func validateTenancyScopedResource(
	value any,
	organizationID string,
	projectID string,
	environmentID string,
	targetAccountID string,
) error {
	switch typed := value.(type) {
	case TenancyOrganization:
		if err := validateTenancyOrganization(typed); err != nil {
			return err
		}
		if organizationID != "" && typed.OrganizationID != organizationID {
			return ErrTenancyUnavailable
		}
	case TenancyProject:
		if err := validateTenancyProject(typed); err != nil {
			return err
		}
		if (organizationID != "" && typed.OrganizationID != organizationID) ||
			(projectID != "" && typed.ProjectID != projectID) {
			return ErrTenancyUnavailable
		}
	case TenancyEnvironment:
		if err := validateTenancyEnvironment(typed); err != nil {
			return err
		}
		if (organizationID != "" && typed.OrganizationID != organizationID) ||
			(projectID != "" && typed.ProjectID != projectID) ||
			(environmentID != "" && typed.EnvironmentID != environmentID) {
			return ErrTenancyUnavailable
		}
	case TenancyProjectMembership:
		if err := validateTenancyProjectMembership(typed); err != nil {
			return err
		}
		if (organizationID != "" && typed.OrganizationID != organizationID) ||
			(projectID != "" && typed.ProjectID != projectID) ||
			(targetAccountID != "" && typed.AccountID != targetAccountID) {
			return ErrTenancyUnavailable
		}
	default:
		return ErrTenancyUnavailable
	}
	return nil
}

func validTenancySlug(value string) bool {
	if len(value) < 3 || len(value) > 64 || value != strings.ToLower(value) {
		return false
	}
	for index, character := range value {
		if (character >= 'a' && character <= 'z') ||
			(index > 0 && character >= '0' && character <= '9') ||
			(index > 0 && index < len(value)-1 && character == '-') {
			continue
		}
		return false
	}
	return true
}

func validTenancyEnvironmentName(value string) bool {
	if len(value) < 3 || len(value) > 64 || value != strings.ToLower(value) {
		return false
	}
	for index, character := range value {
		if (character >= 'a' && character <= 'z') ||
			(index > 0 && character >= '0' && character <= '9') ||
			(index > 0 && index < len(value)-1 &&
				(character == '-' || character == '_')) {
			continue
		}
		return false
	}
	return true
}

func validTenancyEnvironmentKind(value string) bool {
	switch value {
	case "development", "staging", "production", "sandbox":
		return true
	default:
		return false
	}
}

func validTenancyWritableProjectRole(value string) bool {
	switch value {
	case "owner", "admin", "developer", "reviewer", "auditor",
		"read_only_viewer", "service_account":
		return true
	default:
		return false
	}
}

func validTenancyReadableProjectRole(value string) bool {
	return validTenancyWritableProjectRole(value) ||
		value == "operator" || value == "viewer" || value == "member"
}

func validTenancyQueryOperation(value string) bool {
	switch value {
	case TenancyOperationOrganizationList, TenancyOperationProjectList,
		TenancyOperationEnvironmentList, TenancyOperationProjectMembershipList:
		return true
	default:
		return false
	}
}

func validTenancyMutationOperation(value string) bool {
	switch value {
	case TenancyOperationOrganizationCreate, TenancyOperationProjectCreate,
		TenancyOperationProjectUpdate, TenancyOperationProjectArchive,
		TenancyOperationProjectRestore, TenancyOperationEnvironmentCreate,
		TenancyOperationEnvironmentDisable, TenancyOperationEnvironmentEnable,
		TenancyOperationProjectMembershipSet,
		TenancyOperationProjectMembershipRevoke:
		return true
	default:
		return false
	}
}

func tenancyPublicError(err error) (int, string, string) {
	switch {
	case errors.Is(err, ErrTenancyAuthenticationRequired):
		return 401, "tenancy_authentication_required", "authentication is required"
	case errors.Is(err, ErrTenancyInvalidIdempotencyKey):
		return 400, "tenancy_invalid_idempotency_key", "Idempotency-Key is invalid"
	case errors.Is(err, ErrTenancyInvalidRequest):
		return 400, "tenancy_invalid_request", "tenancy request is invalid"
	case errors.Is(err, ErrTenancyIdempotencyConflict):
		return 409, "tenancy_idempotency_conflict", "Idempotency-Key was already used for a different request"
	case errors.Is(err, ErrTenancyForbidden):
		return 403, "tenancy_forbidden", "tenancy operation is forbidden"
	case errors.Is(err, ErrTenancyNotFound):
		return 404, "tenancy_not_found", "tenancy resource was not found"
	case errors.Is(err, ErrTenancyStateConflict):
		return 409, "tenancy_state_conflict", "tenancy lifecycle state conflicts with the operation"
	case errors.Is(err, ErrTenancyLastOwner):
		return 409, "tenancy_last_owner", "project must retain an active owner"
	default:
		return 503, "tenancy_unavailable", "tenancy service is temporarily unavailable"
	}
}

func strictUnmarshalTenancyJSON(payload []byte, target any) error {
	decoder := json.NewDecoder(strings.NewReader(string(payload)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("%w", ErrTenancyUnavailable)
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return ErrTenancyUnavailable
	}
	return nil
}
