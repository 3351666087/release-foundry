from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from http.client import HTTPMessage
from typing import Any, Callable, Generic, Mapping, Sequence, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import json
import re
import ssl
import uuid

from .browser_session import (
    BrowserHTTPResponse,
    BrowserSessionCookieJar,
    BrowserSessionTransport,
)


TENANCY_SCHEMA_VERSION = "releasefoundry.tenancy.v1"
TENANCY_ERROR_CODES = (
    "tenancy_authentication_required",
    "tenancy_invalid_idempotency_key",
    "tenancy_invalid_request",
    "tenancy_idempotency_conflict",
    "tenancy_forbidden",
    "tenancy_not_found",
    "tenancy_state_conflict",
    "tenancy_last_owner",
    "tenancy_unavailable",
)
TENANCY_PROJECT_ROLES = (
    "owner",
    "admin",
    "developer",
    "reviewer",
    "auditor",
    "read_only_viewer",
    "service_account",
)
TENANCY_ENVIRONMENT_KINDS = (
    "development",
    "staging",
    "production",
    "sandbox",
)
TENANCY_ROUTES = (
    ("organization.create", "POST", "/v1/organizations"),
    ("organization.list", "GET", "/v1/organizations"),
    (
        "project.create",
        "POST",
        "/v1/organizations/{organization_id}/projects",
    ),
    (
        "project.list",
        "GET",
        "/v1/organizations/{organization_id}/projects",
    ),
    (
        "project.update",
        "PATCH",
        "/v1/organizations/{organization_id}/projects/{project_id}",
    ),
    (
        "project.archive",
        "POST",
        "/v1/organizations/{organization_id}/projects/{project_id}/archive",
    ),
    (
        "project.restore",
        "POST",
        "/v1/organizations/{organization_id}/projects/{project_id}/restore",
    ),
    (
        "environment.create",
        "POST",
        "/v1/organizations/{organization_id}/projects/{project_id}/environments",
    ),
    (
        "environment.list",
        "GET",
        "/v1/organizations/{organization_id}/projects/{project_id}/environments",
    ),
    (
        "environment.disable",
        "POST",
        "/v1/organizations/{organization_id}/projects/{project_id}/environments/{environment_id}/disable",
    ),
    (
        "environment.enable",
        "POST",
        "/v1/organizations/{organization_id}/projects/{project_id}/environments/{environment_id}/enable",
    ),
    (
        "project_membership.list",
        "GET",
        "/v1/organizations/{organization_id}/projects/{project_id}/memberships",
    ),
    (
        "project_membership.set",
        "PUT",
        "/v1/organizations/{organization_id}/projects/{project_id}/memberships/{account_id}",
    ),
    (
        "project_membership.revoke",
        "DELETE",
        "/v1/organizations/{organization_id}/projects/{project_id}/memberships/{account_id}",
    ),
)

_READABLE_PROJECT_ROLES = frozenset(
    (*TENANCY_PROJECT_ROLES, "operator", "viewer", "member")
)
_PROJECT_STATUSES = frozenset(("active", "archived"))
_ENVIRONMENT_STATUSES = frozenset(("active", "disabled"))
_MEMBERSHIP_STATUSES = frozenset(("invited", "active", "suspended", "revoked"))
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_SLUG_PATTERN = re.compile(r"^[a-z](?:[a-z0-9-]{1,62}[a-z0-9])$")
_ENVIRONMENT_NAME_PATTERN = re.compile(
    r"^[a-z](?:[a-z0-9_-]{1,62}[a-z0-9])$"
)
_CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SUCCESS_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
}
_ERROR_DETAILS: dict[str, tuple[int, str]] = {
    "tenancy_authentication_required": (401, "authentication is required"),
    "tenancy_invalid_idempotency_key": (400, "Idempotency-Key is invalid"),
    "tenancy_invalid_request": (400, "tenancy request is invalid"),
    "tenancy_idempotency_conflict": (
        409,
        "Idempotency-Key was already used for a different request",
    ),
    "tenancy_forbidden": (403, "tenancy operation is forbidden"),
    "tenancy_not_found": (404, "tenancy resource was not found"),
    "tenancy_state_conflict": (
        409,
        "tenancy lifecycle state conflicts with the operation",
    ),
    "tenancy_last_owner": (409, "project must retain an active owner"),
    "tenancy_unavailable": (503, "tenancy service is temporarily unavailable"),
}
_FORBIDDEN_CANONICAL_KEYS = frozenset(
    {
        "actor",
        "actorid",
        "actorprincipalid",
        "principal",
        "principalid",
        "session",
        "sessionid",
        "sessiontoken",
        "sessiondigest",
        "token",
        "cookie",
        "credential",
        "oauth",
        "state",
        "nonce",
        "pkce",
        "proof",
        "ticket",
        "challenge",
        "secretref",
        "privateref",
        "vaultref",
        "kms",
        "ciphertext",
        "requestdigest",
        "payloaddigest",
        "subjectdigest",
        "eventdigest",
        "rawpolicy",
        "rls",
        "acl",
        "sql",
        "databaserole",
        "email",
        "phone",
        "providersubject",
    }
)
_FORBIDDEN_CANONICAL_SUFFIXES = (
    "token",
    "cookie",
    "credential",
    "secretref",
    "privateref",
    "vaultref",
    "ciphertext",
    "digest",
    "ticket",
    "challenge",
    "proof",
)


class TenancyError(RuntimeError):
    """Stable, public-safe tenancy failure."""

    def __init__(
        self,
        code: str,
        *,
        request_id: str = "request_unavailable",
        status: int | None = None,
    ) -> None:
        normalized_code = (
            code if code in _ERROR_DETAILS else "tenancy_unavailable"
        )
        default_status, message = _ERROR_DETAILS[normalized_code]
        self.schema_version = TENANCY_SCHEMA_VERSION
        self.code = normalized_code
        self.request_id = _correlation_id(
            "request_id", request_id, fallback="request_unavailable"
        )
        self.status = default_status if status is None else int(status)
        super().__init__(message)

    def to_public_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "message": str(self),
            "request_id": self.request_id,
        }

    def __repr__(self) -> str:
        return (
            f"TenancyError(code={self.code!r}, status={self.status!r}, "
            f"request_id={self.request_id!r})"
        )


@dataclass(frozen=True)
class TenancyOrganization:
    schema_version: str
    organization_id: str
    slug: str
    display_name: str
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "TenancyOrganization":
        value = _exact_object(
            payload,
            (
                "schema_version",
                "organization_id",
                "slug",
                "display_name",
                "status",
                "created_at",
                "updated_at",
            ),
        )
        result = cls(
            schema_version=_schema_version(value),
            organization_id=_response_uuid(
                "organization_id", value["organization_id"]
            ),
            slug=_response_slug(value["slug"]),
            display_name=_response_display_name(value["display_name"]),
            status=_response_enum("status", value["status"], ("active",)),
            created_at=_timestamp("created_at", value["created_at"]),
            updated_at=_timestamp("updated_at", value["updated_at"]),
        )
        _ordered_timestamps(result.created_at, result.updated_at)
        return result

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class TenancyProject:
    schema_version: str
    organization_id: str
    project_id: str
    slug: str
    display_name: str
    status: str
    created_at: str
    updated_at: str
    archived_at: str | None

    @classmethod
    def from_public_response(
        cls,
        payload: Mapping[str, Any],
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> "TenancyProject":
        value = _exact_object(
            payload,
            (
                "schema_version",
                "organization_id",
                "project_id",
                "slug",
                "display_name",
                "status",
                "created_at",
                "updated_at",
                "archived_at",
            ),
        )
        result = cls(
            schema_version=_schema_version(value),
            organization_id=_response_uuid(
                "organization_id", value["organization_id"]
            ),
            project_id=_response_uuid("project_id", value["project_id"]),
            slug=_response_slug(value["slug"]),
            display_name=_response_display_name(value["display_name"]),
            status=_response_enum("status", value["status"], _PROJECT_STATUSES),
            created_at=_timestamp("created_at", value["created_at"]),
            updated_at=_timestamp("updated_at", value["updated_at"]),
            archived_at=_optional_timestamp("archived_at", value["archived_at"]),
        )
        _ordered_timestamps(result.created_at, result.updated_at)
        if (result.status == "archived") != (result.archived_at is not None):
            raise _invalid_response()
        _expected_scope(
            result.organization_id,
            organization_id,
            result.project_id,
            project_id,
        )
        return result

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class TenancyEnvironment:
    schema_version: str
    organization_id: str
    project_id: str
    environment_id: str
    name: str
    kind: str
    status: str
    created_at: str
    updated_at: str
    disabled_at: str | None

    @classmethod
    def from_public_response(
        cls,
        payload: Mapping[str, Any],
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        environment_id: str | None = None,
    ) -> "TenancyEnvironment":
        value = _exact_object(
            payload,
            (
                "schema_version",
                "organization_id",
                "project_id",
                "environment_id",
                "name",
                "kind",
                "status",
                "created_at",
                "updated_at",
                "disabled_at",
            ),
        )
        result = cls(
            schema_version=_schema_version(value),
            organization_id=_response_uuid(
                "organization_id", value["organization_id"]
            ),
            project_id=_response_uuid("project_id", value["project_id"]),
            environment_id=_response_uuid(
                "environment_id", value["environment_id"]
            ),
            name=_response_environment_name(value["name"]),
            kind=_response_enum(
                "kind", value["kind"], TENANCY_ENVIRONMENT_KINDS
            ),
            status=_response_enum(
                "status", value["status"], _ENVIRONMENT_STATUSES
            ),
            created_at=_timestamp("created_at", value["created_at"]),
            updated_at=_timestamp("updated_at", value["updated_at"]),
            disabled_at=_optional_timestamp("disabled_at", value["disabled_at"]),
        )
        _ordered_timestamps(result.created_at, result.updated_at)
        if (result.status == "disabled") != (result.disabled_at is not None):
            raise _invalid_response()
        _expected_scope(
            result.organization_id,
            organization_id,
            result.project_id,
            project_id,
            result.environment_id,
            environment_id,
        )
        return result

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class TenancyProjectMembership:
    schema_version: str
    organization_id: str
    project_id: str
    account_id: str
    role: str
    status: str
    created_at: str
    updated_at: str
    activated_at: str | None
    revoked_at: str | None

    @classmethod
    def from_public_response(
        cls,
        payload: Mapping[str, Any],
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        account_id: str | None = None,
    ) -> "TenancyProjectMembership":
        value = _exact_object(
            payload,
            (
                "schema_version",
                "organization_id",
                "project_id",
                "account_id",
                "role",
                "status",
                "created_at",
                "updated_at",
                "activated_at",
                "revoked_at",
            ),
        )
        result = cls(
            schema_version=_schema_version(value),
            organization_id=_response_uuid(
                "organization_id", value["organization_id"]
            ),
            project_id=_response_uuid("project_id", value["project_id"]),
            account_id=_response_uuid("account_id", value["account_id"]),
            role=_response_enum("role", value["role"], _READABLE_PROJECT_ROLES),
            status=_response_enum(
                "status", value["status"], _MEMBERSHIP_STATUSES
            ),
            created_at=_timestamp("created_at", value["created_at"]),
            updated_at=_timestamp("updated_at", value["updated_at"]),
            activated_at=_optional_timestamp("activated_at", value["activated_at"]),
            revoked_at=_optional_timestamp("revoked_at", value["revoked_at"]),
        )
        _ordered_timestamps(result.created_at, result.updated_at)
        if result.status == "active" and result.activated_at is None:
            raise _invalid_response()
        if (result.status == "revoked") != (result.revoked_at is not None):
            raise _invalid_response()
        _expected_scope(
            result.organization_id,
            organization_id,
            result.project_id,
            project_id,
            result.account_id,
            account_id,
        )
        return result

    def to_public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


TenancyResource = (
    TenancyOrganization
    | TenancyProject
    | TenancyEnvironment
    | TenancyProjectMembership
)
ResourceT = TypeVar("ResourceT", bound=TenancyResource)


@dataclass(frozen=True)
class TenancyCollection(Generic[ResourceT]):
    schema_version: str
    items: tuple[ResourceT, ...]
    count: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "items": [item.to_public_dict() for item in self.items],
            "count": self.count,
        }


@dataclass(frozen=True)
class TenancyMutationEnvelope(Generic[ResourceT]):
    schema_version: str
    result: ResourceT
    request_id: str
    idempotent_replay: bool

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "result": self.result.to_public_dict(),
            "request_id": self.request_id,
            "idempotent_replay": self.idempotent_replay,
        }


def tenancy_organization_create_route() -> str:
    return "/v1/organizations"


def tenancy_organization_list_route() -> str:
    return "/v1/organizations"


def tenancy_project_list_route(organization_id: str) -> str:
    return f"/v1/organizations/{_uuid('organization_id', organization_id)}/projects"


def tenancy_project_create_route(organization_id: str) -> str:
    return f"/v1/organizations/{_uuid('organization_id', organization_id)}/projects"


def tenancy_project_update_route(organization_id: str, project_id: str) -> str:
    return (
        f"/v1/organizations/{_uuid('organization_id', organization_id)}"
        f"/projects/{_uuid('project_id', project_id)}"
    )


def tenancy_project_archive_route(organization_id: str, project_id: str) -> str:
    return f"{tenancy_project_update_route(organization_id, project_id)}/archive"


def tenancy_project_restore_route(organization_id: str, project_id: str) -> str:
    return f"{tenancy_project_update_route(organization_id, project_id)}/restore"


def tenancy_environment_list_route(
    organization_id: str, project_id: str
) -> str:
    return f"{tenancy_project_update_route(organization_id, project_id)}/environments"


def tenancy_environment_create_route(
    organization_id: str, project_id: str
) -> str:
    return f"{tenancy_project_update_route(organization_id, project_id)}/environments"


def tenancy_environment_disable_route(
    organization_id: str, project_id: str, environment_id: str
) -> str:
    return (
        f"{tenancy_environment_list_route(organization_id, project_id)}"
        f"/{_uuid('environment_id', environment_id)}/disable"
    )


def tenancy_environment_enable_route(
    organization_id: str, project_id: str, environment_id: str
) -> str:
    return (
        f"{tenancy_environment_list_route(organization_id, project_id)}"
        f"/{_uuid('environment_id', environment_id)}/enable"
    )


def tenancy_project_membership_list_route(
    organization_id: str, project_id: str
) -> str:
    return f"{tenancy_project_update_route(organization_id, project_id)}/memberships"


def tenancy_project_membership_set_route(
    organization_id: str, project_id: str, account_id: str
) -> str:
    return (
        f"{tenancy_project_membership_list_route(organization_id, project_id)}"
        f"/{_uuid('account_id', account_id)}"
    )


def tenancy_project_membership_revoke_route(
    organization_id: str, project_id: str, account_id: str
) -> str:
    return tenancy_project_membership_set_route(
        organization_id, project_id, account_id
    )


Parser = Callable[[Mapping[str, Any]], ResourceT]


class TenancyClient:
    """Cookie-authenticated tenancy client with no caller-controlled principal."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: BrowserSessionTransport | None = None,
        cookie_jar: BrowserSessionCookieJar | None = None,
        timeout_seconds: float = 30.0,
        allow_insecure_localhost: bool = False,
    ) -> None:
        self.origin = _normalize_origin(base_url, allow_insecure_localhost)
        self.base_url = self.origin
        self.cookie_jar = cookie_jar or BrowserSessionCookieJar(self.origin)
        if self.cookie_jar._origin != self.origin:
            raise TenancyError("tenancy_invalid_request")
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise TenancyError("tenancy_invalid_request")
        self.timeout_seconds = float(timeout_seconds)
        self._transport = transport or self._default_transport

    def create_organization(
        self, slug: str, display_name: str, *, idempotency_key: str
    ) -> TenancyMutationEnvelope[TenancyOrganization]:
        return self._mutate(
            "POST",
            tenancy_organization_create_route(),
            {"slug": _slug(slug), "display_name": _display_name(display_name)},
            idempotency_key,
            201,
            TenancyOrganization.from_public_response,
        )

    def list_organizations(self) -> TenancyCollection[TenancyOrganization]:
        return self._list(
            tenancy_organization_list_route(),
            TenancyOrganization.from_public_response,
        )

    def list_projects(
        self, organization_id: str
    ) -> TenancyCollection[TenancyProject]:
        organization = _uuid("organization_id", organization_id)
        return self._list(
            tenancy_project_list_route(organization),
            lambda value: TenancyProject.from_public_response(
                value, organization_id=organization
            ),
        )

    def create_project(
        self,
        organization_id: str,
        slug: str,
        display_name: str,
        *,
        idempotency_key: str,
    ) -> TenancyMutationEnvelope[TenancyProject]:
        organization = _uuid("organization_id", organization_id)
        return self._mutate(
            "POST",
            tenancy_project_create_route(organization),
            {"slug": _slug(slug), "display_name": _display_name(display_name)},
            idempotency_key,
            201,
            lambda value: TenancyProject.from_public_response(
                value, organization_id=organization
            ),
        )

    def update_project(
        self,
        organization_id: str,
        project_id: str,
        *,
        idempotency_key: str,
        slug: str | None = None,
        display_name: str | None = None,
    ) -> TenancyMutationEnvelope[TenancyProject]:
        organization = _uuid("organization_id", organization_id)
        project = _uuid("project_id", project_id)
        payload: dict[str, Any] = {}
        if slug is not None:
            payload["slug"] = _slug(slug)
        if display_name is not None:
            payload["display_name"] = _display_name(display_name)
        if not payload:
            raise TenancyError("tenancy_invalid_request")
        return self._mutate(
            "PATCH",
            tenancy_project_update_route(organization, project),
            payload,
            idempotency_key,
            200,
            lambda value: TenancyProject.from_public_response(
                value, organization_id=organization, project_id=project
            ),
        )

    def archive_project(
        self, organization_id: str, project_id: str, *, idempotency_key: str
    ) -> TenancyMutationEnvelope[TenancyProject]:
        return self._project_state_mutation(
            organization_id, project_id, "archive", idempotency_key
        )

    def restore_project(
        self, organization_id: str, project_id: str, *, idempotency_key: str
    ) -> TenancyMutationEnvelope[TenancyProject]:
        return self._project_state_mutation(
            organization_id, project_id, "restore", idempotency_key
        )

    def list_environments(
        self, organization_id: str, project_id: str
    ) -> TenancyCollection[TenancyEnvironment]:
        organization = _uuid("organization_id", organization_id)
        project = _uuid("project_id", project_id)
        return self._list(
            tenancy_environment_list_route(organization, project),
            lambda value: TenancyEnvironment.from_public_response(
                value, organization_id=organization, project_id=project
            ),
        )

    def create_environment(
        self,
        organization_id: str,
        project_id: str,
        name: str,
        kind: str,
        *,
        idempotency_key: str,
    ) -> TenancyMutationEnvelope[TenancyEnvironment]:
        organization = _uuid("organization_id", organization_id)
        project = _uuid("project_id", project_id)
        return self._mutate(
            "POST",
            tenancy_environment_create_route(organization, project),
            {
                "name": _environment_name(name),
                "kind": _enum("kind", kind, TENANCY_ENVIRONMENT_KINDS),
            },
            idempotency_key,
            201,
            lambda value: TenancyEnvironment.from_public_response(
                value, organization_id=organization, project_id=project
            ),
        )

    def disable_environment(
        self,
        organization_id: str,
        project_id: str,
        environment_id: str,
        *,
        idempotency_key: str,
    ) -> TenancyMutationEnvelope[TenancyEnvironment]:
        return self._environment_state_mutation(
            organization_id,
            project_id,
            environment_id,
            "disable",
            idempotency_key,
        )

    def enable_environment(
        self,
        organization_id: str,
        project_id: str,
        environment_id: str,
        *,
        idempotency_key: str,
    ) -> TenancyMutationEnvelope[TenancyEnvironment]:
        return self._environment_state_mutation(
            organization_id,
            project_id,
            environment_id,
            "enable",
            idempotency_key,
        )

    def list_project_memberships(
        self, organization_id: str, project_id: str
    ) -> TenancyCollection[TenancyProjectMembership]:
        organization = _uuid("organization_id", organization_id)
        project = _uuid("project_id", project_id)
        return self._list(
            tenancy_project_membership_list_route(organization, project),
            lambda value: TenancyProjectMembership.from_public_response(
                value, organization_id=organization, project_id=project
            ),
        )

    def set_project_membership(
        self,
        organization_id: str,
        project_id: str,
        account_id: str,
        role: str,
        *,
        idempotency_key: str,
    ) -> TenancyMutationEnvelope[TenancyProjectMembership]:
        organization = _uuid("organization_id", organization_id)
        project = _uuid("project_id", project_id)
        account = _uuid("account_id", account_id)
        return self._mutate(
            "PUT",
            tenancy_project_membership_set_route(
                organization, project, account
            ),
            {"role": _enum("role", role, TENANCY_PROJECT_ROLES)},
            idempotency_key,
            200,
            lambda value: TenancyProjectMembership.from_public_response(
                value,
                organization_id=organization,
                project_id=project,
                account_id=account,
            ),
        )

    def revoke_project_membership(
        self,
        organization_id: str,
        project_id: str,
        account_id: str,
        *,
        idempotency_key: str,
    ) -> TenancyMutationEnvelope[TenancyProjectMembership]:
        organization = _uuid("organization_id", organization_id)
        project = _uuid("project_id", project_id)
        account = _uuid("account_id", account_id)
        return self._mutate(
            "DELETE",
            tenancy_project_membership_revoke_route(
                organization, project, account
            ),
            {},
            idempotency_key,
            200,
            lambda value: TenancyProjectMembership.from_public_response(
                value,
                organization_id=organization,
                project_id=project,
                account_id=account,
            ),
        )

    def _project_state_mutation(
        self,
        organization_id: str,
        project_id: str,
        operation: str,
        idempotency_key: str,
    ) -> TenancyMutationEnvelope[TenancyProject]:
        organization = _uuid("organization_id", organization_id)
        project = _uuid("project_id", project_id)
        route = (
            tenancy_project_archive_route(organization, project)
            if operation == "archive"
            else tenancy_project_restore_route(organization, project)
        )
        return self._mutate(
            "POST",
            route,
            {},
            idempotency_key,
            200,
            lambda value: TenancyProject.from_public_response(
                value, organization_id=organization, project_id=project
            ),
        )

    def _environment_state_mutation(
        self,
        organization_id: str,
        project_id: str,
        environment_id: str,
        operation: str,
        idempotency_key: str,
    ) -> TenancyMutationEnvelope[TenancyEnvironment]:
        organization = _uuid("organization_id", organization_id)
        project = _uuid("project_id", project_id)
        environment = _uuid("environment_id", environment_id)
        route = (
            tenancy_environment_disable_route(
                organization, project, environment
            )
            if operation == "disable"
            else tenancy_environment_enable_route(
                organization, project, environment
            )
        )
        return self._mutate(
            "POST",
            route,
            {},
            idempotency_key,
            200,
            lambda value: TenancyEnvironment.from_public_response(
                value,
                organization_id=organization,
                project_id=project,
                environment_id=environment,
            ),
        )

    def _list(
        self, path: str, parser: Parser[ResourceT]
    ) -> TenancyCollection[ResourceT]:
        response = self._request("GET", path, None, None, 200)
        payload = _exact_object(
            _decode_response(response),
            ("schema_version", "items", "count"),
        )
        _schema_version(payload)
        raw_items = payload["items"]
        count = payload["count"]
        if (
            not isinstance(raw_items, list)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or count != len(raw_items)
        ):
            raise _invalid_response()
        items = tuple(parser(_mapping(item)) for item in raw_items)
        return TenancyCollection(TENANCY_SCHEMA_VERSION, items, count)

    def _mutate(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        success_status: int,
        parser: Parser[ResourceT],
    ) -> TenancyMutationEnvelope[ResourceT]:
        _assert_public_safe(payload)
        response = self._request(
            method,
            path,
            payload,
            _idempotency_key(idempotency_key),
            success_status,
        )
        envelope = _exact_object(
            _decode_response(response),
            (
                "schema_version",
                "result",
                "request_id",
                "idempotent_replay",
            ),
        )
        _schema_version(envelope)
        replay = envelope["idempotent_replay"]
        if not isinstance(replay, bool):
            raise _invalid_response()
        return TenancyMutationEnvelope(
            TENANCY_SCHEMA_VERSION,
            parser(_mapping(envelope["result"])),
            _correlation_id("request_id", envelope["request_id"]),
            replay,
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None,
        idempotency_key: str | None,
        success_status: int,
    ) -> BrowserHTTPResponse:
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Cache-Control": "no-store",
            "Origin": self.origin,
            "Pragma": "no-cache",
            "Sec-Fetch-Site": "same-origin",
        }
        body: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(
                payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True
            ).encode("utf-8")
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        cookie_header = self.cookie_jar._request_cookie_header(url)
        if cookie_header is not None:
            headers["Cookie"] = cookie_header
        try:
            response = self._transport(method, url, headers, body)
        except TenancyError:
            raise
        except Exception as exc:
            raise TenancyError("tenancy_unavailable") from exc
        if not isinstance(response, BrowserHTTPResponse):
            raise _invalid_response()
        try:
            self.cookie_jar.ingest(response)
        except Exception as exc:
            raise _invalid_response() from exc
        if response.status != success_status:
            raise _error_from_response(response)
        _validate_response_headers(response)
        return response

    def _default_transport(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> BrowserHTTPResponse:
        context = ssl.create_default_context()
        opener = build_opener(_NoRedirect(), HTTPSHandler(context=context))
        request = Request(url, data=body, headers=dict(headers), method=method)
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                return BrowserHTTPResponse(
                    status=response.status,
                    headers=tuple(response.headers.items()),
                    body=response.read(1_048_577),
                )
        except HTTPError as exc:
            return BrowserHTTPResponse(
                status=exc.code,
                headers=tuple(_headers_items(exc.headers)),
                body=exc.read(1_048_577),
            )
        except (URLError, TimeoutError, OSError) as exc:
            raise TenancyError("tenancy_unavailable") from exc


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _headers_items(headers: HTTPMessage | None) -> Sequence[tuple[str, str]]:
    return () if headers is None else tuple(headers.items())


def _error_from_response(response: BrowserHTTPResponse) -> TenancyError:
    try:
        payload = _exact_object(
            _decode_response(response),
            ("schema_version", "code", "message", "request_id"),
        )
        _schema_version(payload)
        code = payload["code"]
        if not isinstance(code, str) or code not in TENANCY_ERROR_CODES:
            raise _invalid_response()
        expected_status, canonical_message = _ERROR_DETAILS[code]
        if (
            payload["message"] != canonical_message
            or response.status != expected_status
        ):
            raise _invalid_response()
        request_id = _correlation_id("request_id", payload["request_id"])
        _validate_response_headers(response)
        return TenancyError(code, request_id=request_id, status=response.status)
    except TenancyError as exc:
        if exc.code == "tenancy_unavailable" and exc.request_id == "request_unavailable":
            return exc
        raise
    except Exception:
        return _invalid_response()


def _validate_response_headers(response: BrowserHTTPResponse) -> None:
    for name, expected in _SUCCESS_HEADERS.items():
        values = response.header_values(name)
        if len(values) != 1 or values[0].strip().lower() != expected:
            raise _invalid_response()
    content_types = response.header_values("content-type")
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != (
        "application/json"
    ):
        raise _invalid_response()


def _decode_response(response: BrowserHTTPResponse) -> Mapping[str, Any]:
    body = response.body
    if isinstance(body, Mapping):
        value: Any = dict(body)
    else:
        if isinstance(body, str):
            encoded = body.encode("utf-8")
        elif isinstance(body, bytes):
            encoded = body
        else:
            raise _invalid_response()
        if len(encoded) > 1_048_576:
            raise _invalid_response()
        try:
            value = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _invalid_response() from exc
    if not isinstance(value, Mapping):
        raise _invalid_response()
    result = dict(value)
    _assert_public_safe(result)
    return result


def _exact_object(
    payload: Mapping[str, Any], keys: Sequence[str]
) -> dict[str, Any]:
    value = _mapping(payload)
    _assert_public_safe(value)
    if set(value) != set(keys) or len(value) != len(keys):
        raise _invalid_response()
    return value


def _mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _invalid_response()
    return dict(value)


def _schema_version(value: Mapping[str, Any]) -> str:
    if value.get("schema_version") != TENANCY_SCHEMA_VERSION:
        raise _invalid_response()
    return TENANCY_SCHEMA_VERSION


def _uuid(name: str, value: Any) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise TenancyError("tenancy_invalid_request")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise TenancyError("tenancy_invalid_request") from exc
    canonical = str(parsed)
    if value.lower() != canonical:
        raise TenancyError("tenancy_invalid_request")
    return canonical


def _slug(value: Any) -> str:
    if not isinstance(value, str):
        raise TenancyError("tenancy_invalid_request")
    normalized = value.strip().lower()
    if not _SLUG_PATTERN.fullmatch(normalized):
        raise TenancyError("tenancy_invalid_request")
    return normalized


def _environment_name(value: Any) -> str:
    if not isinstance(value, str):
        raise TenancyError("tenancy_invalid_request")
    normalized = value.strip().lower()
    if not _ENVIRONMENT_NAME_PATTERN.fullmatch(normalized):
        raise TenancyError("tenancy_invalid_request")
    return normalized


def _display_name(value: Any) -> str:
    if not isinstance(value, str):
        raise TenancyError("tenancy_invalid_request")
    normalized = value.strip()
    if not normalized or len(normalized) > 120 or "\x00" in normalized:
        raise TenancyError("tenancy_invalid_request")
    return normalized


def _enum(name: str, value: Any, allowed: Sequence[str] | frozenset[str]) -> str:
    if not isinstance(value, str):
        raise TenancyError("tenancy_invalid_request")
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise TenancyError("tenancy_invalid_request")
    return normalized


def _idempotency_key(value: Any) -> str:
    if not isinstance(value, str) or not _IDEMPOTENCY_PATTERN.fullmatch(value):
        raise TenancyError("tenancy_invalid_idempotency_key")
    return value


def _response_uuid(name: str, value: Any) -> str:
    try:
        return _uuid(name, value)
    except TenancyError as exc:
        raise _invalid_response() from exc


def _response_slug(value: Any) -> str:
    try:
        return _slug(value)
    except TenancyError as exc:
        raise _invalid_response() from exc


def _response_environment_name(value: Any) -> str:
    try:
        return _environment_name(value)
    except TenancyError as exc:
        raise _invalid_response() from exc


def _response_display_name(value: Any) -> str:
    try:
        return _display_name(value)
    except TenancyError as exc:
        raise _invalid_response() from exc


def _response_enum(
    name: str, value: Any, allowed: Sequence[str] | frozenset[str]
) -> str:
    try:
        return _enum(name, value, allowed)
    except TenancyError as exc:
        raise _invalid_response() from exc


def _correlation_id(name: str, value: Any, *, fallback: str | None = None) -> str:
    if isinstance(value, str) and _CORRELATION_PATTERN.fullmatch(value):
        return value
    if fallback is not None:
        return fallback
    raise _invalid_response()


def _timestamp(name: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 64
    ):
        raise _invalid_response()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid_response() from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _invalid_response()
    return value


def _optional_timestamp(name: str, value: Any) -> str | None:
    return None if value is None else _timestamp(name, value)


def _ordered_timestamps(created_at: str, updated_at: str) -> None:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    if updated < created:
        raise _invalid_response()


def _expected_scope(*pairs: str | None) -> None:
    for index in range(0, len(pairs), 2):
        actual = pairs[index]
        expected = pairs[index + 1]
        if expected is not None and actual != expected:
            raise _invalid_response()


def _assert_public_safe(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = "".join(
                character
                for character in str(key).strip().lower()
                if character.isalnum()
            )
            if normalized in _FORBIDDEN_CANONICAL_KEYS or normalized.endswith(
                _FORBIDDEN_CANONICAL_SUFFIXES
            ):
                raise _invalid_response()
            _assert_public_safe(item)
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for item in value:
            _assert_public_safe(item)


def _normalize_origin(value: str, allow_insecure_localhost: bool) -> str:
    try:
        parsed = urlsplit(str(value).strip())
        host = parsed.hostname or ""
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise TenancyError("tenancy_invalid_request") from exc
    if (
        not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise TenancyError("tenancy_invalid_request")
    if parsed.scheme != "https":
        controlled = host in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "http" or not allow_insecure_localhost or not controlled:
            raise TenancyError("tenancy_invalid_request")
    normalized_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    authority = normalized_host if port is None else f"{normalized_host}:{port}"
    return f"{parsed.scheme}://{authority}"


def _invalid_response() -> TenancyError:
    return TenancyError("tenancy_unavailable")


__all__ = [
    "TENANCY_ENVIRONMENT_KINDS",
    "TENANCY_ERROR_CODES",
    "TENANCY_PROJECT_ROLES",
    "TENANCY_SCHEMA_VERSION",
    "TenancyClient",
    "TenancyCollection",
    "TenancyEnvironment",
    "TenancyError",
    "TenancyMutationEnvelope",
    "TenancyOrganization",
    "TenancyProject",
    "TenancyProjectMembership",
    "tenancy_environment_create_route",
    "tenancy_environment_disable_route",
    "tenancy_environment_enable_route",
    "tenancy_environment_list_route",
    "tenancy_organization_create_route",
    "tenancy_organization_list_route",
    "tenancy_project_archive_route",
    "tenancy_project_create_route",
    "tenancy_project_list_route",
    "tenancy_project_membership_list_route",
    "tenancy_project_membership_revoke_route",
    "tenancy_project_membership_set_route",
    "tenancy_project_restore_route",
    "tenancy_project_update_route",
]
