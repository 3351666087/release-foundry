from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import json

import pytest

import releasefoundry
from releasefoundry.browser_session import (
    BROWSER_SESSION_COOKIE_NAMES,
    BrowserHTTPResponse,
    BrowserSessionCookieJar,
)
from releasefoundry.tenancy import (
    TENANCY_ROUTES,
    TENANCY_SCHEMA_VERSION,
    TenancyClient,
    TenancyError,
    TenancyOrganization,
    tenancy_environment_create_route,
    tenancy_environment_disable_route,
    tenancy_environment_enable_route,
    tenancy_environment_list_route,
    tenancy_organization_create_route,
    tenancy_organization_list_route,
    tenancy_project_archive_route,
    tenancy_project_create_route,
    tenancy_project_list_route,
    tenancy_project_membership_list_route,
    tenancy_project_membership_revoke_route,
    tenancy_project_membership_set_route,
    tenancy_project_restore_route,
    tenancy_project_update_route,
)


ORGANIZATION_ID = "33333333-3333-4333-8333-333333333333"
PROJECT_ID = "44444444-4444-4444-8444-444444444444"
ENVIRONMENT_ID = "55555555-5555-4555-8555-555555555555"
ACCOUNT_ID = "66666666-6666-4666-8666-666666666666"
NOW = "2026-07-25T01:02:03Z"
SECURE_HEADERS = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def organization() -> dict[str, object]:
    return {
        "schema_version": TENANCY_SCHEMA_VERSION,
        "organization_id": ORGANIZATION_ID,
        "slug": "acme-org",
        "display_name": "Acme",
        "status": "active",
        "created_at": NOW,
        "updated_at": NOW,
    }


def project(*, status: str = "active") -> dict[str, object]:
    return {
        "schema_version": TENANCY_SCHEMA_VERSION,
        "organization_id": ORGANIZATION_ID,
        "project_id": PROJECT_ID,
        "slug": "core-api",
        "display_name": "Core API",
        "status": status,
        "created_at": NOW,
        "updated_at": NOW,
        "archived_at": NOW if status == "archived" else None,
    }


def environment(*, status: str = "active") -> dict[str, object]:
    return {
        "schema_version": TENANCY_SCHEMA_VERSION,
        "organization_id": ORGANIZATION_ID,
        "project_id": PROJECT_ID,
        "environment_id": ENVIRONMENT_ID,
        "name": "prod-cn",
        "kind": "production",
        "status": status,
        "created_at": NOW,
        "updated_at": NOW,
        "disabled_at": NOW if status == "disabled" else None,
    }


def membership(*, status: str = "active") -> dict[str, object]:
    return {
        "schema_version": TENANCY_SCHEMA_VERSION,
        "organization_id": ORGANIZATION_ID,
        "project_id": PROJECT_ID,
        "account_id": ACCOUNT_ID,
        "role": "developer",
        "status": status,
        "created_at": NOW,
        "updated_at": NOW,
        "activated_at": NOW,
        "revoked_at": NOW if status == "revoked" else None,
    }


def success(status: int, payload: dict[str, object]) -> BrowserHTTPResponse:
    return BrowserHTTPResponse.create(status, headers=SECURE_HEADERS, body=payload)


def mutation(resource: dict[str, object], *, replay: bool = False) -> dict[str, object]:
    return {
        "schema_version": TENANCY_SCHEMA_VERSION,
        "result": resource,
        "request_id": "request_test_001",
        "idempotent_replay": replay,
    }


def test_fourteen_exact_route_helpers_are_frozen() -> None:
    assert len(TENANCY_ROUTES) == 14
    assert TENANCY_ROUTES == (
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
    assert tenancy_organization_create_route() == "/v1/organizations"
    assert tenancy_organization_list_route() == "/v1/organizations"
    projects = f"/v1/organizations/{ORGANIZATION_ID}/projects"
    assert tenancy_project_list_route(ORGANIZATION_ID) == projects
    assert tenancy_project_create_route(ORGANIZATION_ID) == projects
    selected = f"{projects}/{PROJECT_ID}"
    assert tenancy_project_update_route(ORGANIZATION_ID, PROJECT_ID) == selected
    assert tenancy_project_archive_route(ORGANIZATION_ID, PROJECT_ID) == f"{selected}/archive"
    assert tenancy_project_restore_route(ORGANIZATION_ID, PROJECT_ID) == f"{selected}/restore"
    environments = f"{selected}/environments"
    assert tenancy_environment_list_route(ORGANIZATION_ID, PROJECT_ID) == environments
    assert tenancy_environment_create_route(ORGANIZATION_ID, PROJECT_ID) == environments
    assert tenancy_environment_disable_route(
        ORGANIZATION_ID, PROJECT_ID, ENVIRONMENT_ID
    ) == f"{environments}/{ENVIRONMENT_ID}/disable"
    assert tenancy_environment_enable_route(
        ORGANIZATION_ID, PROJECT_ID, ENVIRONMENT_ID
    ) == f"{environments}/{ENVIRONMENT_ID}/enable"
    memberships = f"{selected}/memberships"
    assert tenancy_project_membership_list_route(ORGANIZATION_ID, PROJECT_ID) == memberships
    assert tenancy_project_membership_set_route(
        ORGANIZATION_ID, PROJECT_ID, ACCOUNT_ID
    ) == f"{memberships}/{ACCOUNT_ID}"
    assert tenancy_project_membership_revoke_route(
        ORGANIZATION_ID, PROJECT_ID, ACCOUNT_ID
    ) == f"{memberships}/{ACCOUNT_ID}"


def test_cookie_authenticated_create_uses_header_only_idempotency_without_logging_value() -> None:
    jar = BrowserSessionCookieJar("https://api.example.test")
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    cookie_value = "opaque-browser-session"
    jar.ingest(
        BrowserHTTPResponse.create(
            200,
            headers={
                "Set-Cookie": (
                    f"{BROWSER_SESSION_COOKIE_NAMES[0]}={cookie_value}; Path=/; "
                    f"Expires={expires.strftime('%a, %d %b %Y %H:%M:%S GMT')}; "
                    "Max-Age=300; HttpOnly; Secure; SameSite=Strict"
                )
            },
        )
    )
    observed: dict[str, object] = {}

    def transport(method, url, headers, body):  # type: ignore[no-untyped-def]
        observed.update(
            method=method,
            url=url,
            header_names=tuple(sorted(headers)),
            cookie_present="Cookie" in headers,
            idempotency_key=headers.get("Idempotency-Key"),
            body=json.loads(body or b"{}"),
        )
        assert cookie_value in headers["Cookie"]
        return success(201, mutation(organization()))

    client = TenancyClient(
        "https://api.example.test", transport=transport, cookie_jar=jar
    )
    result = client.create_organization(
        " ACME-ORG ", " Acme ", idempotency_key="idem-python-0001"
    )

    assert observed == {
        "method": "POST",
        "url": "https://api.example.test/v1/organizations",
        "header_names": (
            "Accept",
            "Cache-Control",
            "Content-Type",
            "Cookie",
            "Idempotency-Key",
            "Origin",
            "Pragma",
            "Sec-Fetch-Site",
        ),
        "cookie_present": True,
        "idempotency_key": "idem-python-0001",
        "body": {"display_name": "Acme", "slug": "acme-org"},
    }
    assert "idempotency_key" not in observed["body"]
    assert result.result.organization_id == ORGANIZATION_ID
    rendered = json.dumps(result.to_public_dict(), sort_keys=True) + repr(client.cookie_jar)
    assert cookie_value not in rendered


def test_all_fourteen_client_operations_match_methods_bodies_and_scopes() -> None:
    scripted = [
        success(201, mutation(organization())),
        success(200, {"schema_version": TENANCY_SCHEMA_VERSION, "items": [organization()], "count": 1}),
        success(200, {"schema_version": TENANCY_SCHEMA_VERSION, "items": [project()], "count": 1}),
        success(201, mutation(project())),
        success(200, mutation(project())),
        success(200, mutation(project(status="archived"))),
        success(200, mutation(project())),
        success(200, {"schema_version": TENANCY_SCHEMA_VERSION, "items": [environment()], "count": 1}),
        success(201, mutation(environment())),
        success(200, mutation(environment(status="disabled"))),
        success(200, mutation(environment())),
        success(200, {"schema_version": TENANCY_SCHEMA_VERSION, "items": [membership()], "count": 1}),
        success(200, mutation(membership())),
        success(200, mutation(membership(status="revoked"))),
    ]
    calls: list[tuple[str, str, dict[str, object] | None, str | None]] = []

    def transport(method, url, headers, body):  # type: ignore[no-untyped-def]
        calls.append(
            (
                method,
                url.removeprefix("https://api.example.test"),
                None if body is None else json.loads(body),
                headers.get("Idempotency-Key"),
            )
        )
        return scripted.pop(0)

    client = TenancyClient("https://api.example.test", transport=transport)
    key = "idem-python-0002"
    client.create_organization("acme-org", "Acme", idempotency_key=key)
    client.list_organizations()
    client.list_projects(ORGANIZATION_ID)
    client.create_project(ORGANIZATION_ID, "core-api", "Core API", idempotency_key=key)
    client.update_project(ORGANIZATION_ID, PROJECT_ID, display_name="Core API", idempotency_key=key)
    client.archive_project(ORGANIZATION_ID, PROJECT_ID, idempotency_key=key)
    client.restore_project(ORGANIZATION_ID, PROJECT_ID, idempotency_key=key)
    client.list_environments(ORGANIZATION_ID, PROJECT_ID)
    client.create_environment(
        ORGANIZATION_ID, PROJECT_ID, "prod-cn", "production", idempotency_key=key
    )
    client.disable_environment(
        ORGANIZATION_ID, PROJECT_ID, ENVIRONMENT_ID, idempotency_key=key
    )
    client.enable_environment(
        ORGANIZATION_ID, PROJECT_ID, ENVIRONMENT_ID, idempotency_key=key
    )
    client.list_project_memberships(ORGANIZATION_ID, PROJECT_ID)
    client.set_project_membership(
        ORGANIZATION_ID, PROJECT_ID, ACCOUNT_ID, "developer", idempotency_key=key
    )
    client.revoke_project_membership(
        ORGANIZATION_ID, PROJECT_ID, ACCOUNT_ID, idempotency_key=key
    )

    assert [call[0] for call in calls] == [
        "POST", "GET", "GET", "POST", "PATCH", "POST", "POST",
        "GET", "POST", "POST", "POST", "GET", "PUT", "DELETE",
    ]
    for method, _, body, idempotency in calls:
        if method == "GET":
            assert body is None and idempotency is None
        else:
            assert idempotency == key
            assert isinstance(body, dict)
            assert "idempotency_key" not in body
            assert not {
                "actor_id",
                "actor_principal_id",
                "principal_id",
                "session_id",
                "account_id",
            }.intersection(body)
    assert calls[-2][2] == {"role": "developer"}
    assert ACCOUNT_ID in calls[-2][1] and ACCOUNT_ID in calls[-1][1]


@pytest.mark.parametrize(
    "private_field",
    [
        "actor_id",
        "session_token",
        "oauth_state",
        "pkce",
        "secret_ref",
        "vault_ref",
        "request_digest",
        "raw_policy",
        "database_role",
        "provider_subject",
    ],
)
def test_response_parser_rejects_recursive_private_markers(private_field: str) -> None:
    payload = organization()
    payload[private_field] = {"nested": "not-public"}
    client = TenancyClient(
        "https://api.example.test",
        transport=lambda *_: success(
            200,
            {
                "schema_version": TENANCY_SCHEMA_VERSION,
                "items": [payload],
                "count": 1,
            },
        ),
    )
    with pytest.raises(TenancyError) as captured:
        client.list_organizations()
    assert captured.value.code == "tenancy_unavailable"
    assert set(captured.value.to_public_dict()) == {
        "schema_version",
        "code",
        "message",
        "request_id",
    }


def test_exact_key_count_and_cross_scope_validation_fail_closed() -> None:
    wrong = project()
    wrong["organization_id"] = ACCOUNT_ID
    invalid_identifier = organization()
    invalid_identifier["organization_id"] = "not-a-uuid"
    responses = [
        success(
            200,
            {
                "schema_version": TENANCY_SCHEMA_VERSION,
                "items": [wrong],
                "count": 1,
            },
        ),
        success(
            200,
            {
                "schema_version": TENANCY_SCHEMA_VERSION,
                "items": [],
                "count": 1,
            },
        ),
        success(
            201,
            {
                **mutation(organization()),
                "request_digest": "not-public",
            },
        ),
        success(
            200,
            {
                "schema_version": TENANCY_SCHEMA_VERSION,
                "items": [invalid_identifier],
                "count": 1,
            },
        ),
    ]
    client = TenancyClient(
        "https://api.example.test", transport=lambda *_: responses.pop(0)
    )
    with pytest.raises(TenancyError):
        client.list_projects(ORGANIZATION_ID)
    with pytest.raises(TenancyError):
        client.list_organizations()
    with pytest.raises(TenancyError):
        client.create_organization("acme-org", "Acme", idempotency_key="idem-python-0003")
    with pytest.raises(TenancyError) as malformed_identifier:
        client.list_organizations()
    assert malformed_identifier.value.code == "tenancy_unavailable"


def test_error_response_accepts_only_exact_stable_envelope() -> None:
    valid = BrowserHTTPResponse.create(
        409,
        headers=SECURE_HEADERS,
        body={
            "schema_version": TENANCY_SCHEMA_VERSION,
            "code": "tenancy_last_owner",
            "message": "project must retain an active owner",
            "request_id": "request_test_002",
        },
    )
    client = TenancyClient("https://api.example.test", transport=lambda *_: valid)
    with pytest.raises(TenancyError) as captured:
        client.revoke_project_membership(
            ORGANIZATION_ID,
            PROJECT_ID,
            ACCOUNT_ID,
            idempotency_key="idem-python-0004",
        )
    assert captured.value.to_public_dict() == {
        "schema_version": TENANCY_SCHEMA_VERSION,
        "code": "tenancy_last_owner",
        "message": "project must retain an active owner",
        "request_id": "request_test_002",
    }

    malformed = BrowserHTTPResponse.create(
        409,
        headers=SECURE_HEADERS,
        body={**valid.body, "sql": "private detail"},  # type: ignore[arg-type]
    )
    client = TenancyClient("https://api.example.test", transport=lambda *_: malformed)
    with pytest.raises(TenancyError) as rejected:
        client.revoke_project_membership(
            ORGANIZATION_ID,
            PROJECT_ID,
            ACCOUNT_ID,
            idempotency_key="idem-python-0005",
        )
    assert rejected.value.code == "tenancy_unavailable"
    assert "private detail" not in str(rejected.value)


def test_https_default_localhost_opt_in_and_origin_bound_cookie_jar() -> None:
    with pytest.raises(TenancyError):
        TenancyClient("http://localhost:8787")
    assert TenancyClient(
        "http://localhost:8787",
        allow_insecure_localhost=True,
        transport=lambda *_: success(
            200,
            {"schema_version": TENANCY_SCHEMA_VERSION, "items": [], "count": 0},
        ),
    ).origin == "http://localhost:8787"
    with pytest.raises(TenancyError):
        TenancyClient("http://example.test", allow_insecure_localhost=True)
    wrong_jar = BrowserSessionCookieJar("https://other.example.test")
    with pytest.raises(TenancyError):
        TenancyClient("https://api.example.test", cookie_jar=wrong_jar)


def test_frozen_dtos_input_validation_security_headers_and_root_exports() -> None:
    dto = TenancyOrganization.from_public_response(organization())
    with pytest.raises(FrozenInstanceError):
        dto.slug = "changed"  # type: ignore[misc]
    assert releasefoundry.TenancyClient is TenancyClient
    assert releasefoundry.TENANCY_ROUTES is TENANCY_ROUTES
    assert releasefoundry.TENANCY_SCHEMA_VERSION == TENANCY_SCHEMA_VERSION

    with pytest.raises(TenancyError) as invalid_key:
        TenancyClient("https://api.example.test", transport=lambda *_: success(201, mutation(organization()))).create_organization(
            "acme-org", "Acme", idempotency_key="short"
        )
    assert invalid_key.value.code == "tenancy_invalid_idempotency_key"

    missing_headers = BrowserHTTPResponse.create(
        200,
        headers={"Content-Type": "application/json"},
        body={"schema_version": TENANCY_SCHEMA_VERSION, "items": [], "count": 0},
    )
    with pytest.raises(TenancyError):
        TenancyClient(
            "https://api.example.test", transport=lambda *_: missing_headers
        ).list_organizations()
