from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from releasefoundry import a3_identity_contract_manifest


ROOT = Path(__file__).resolve().parents[2]
GO_SERVER = ROOT / "packages/go/releasefoundry/server.go"
TS_IDENTITY = ROOT / "packages/ts/releasefoundry/src/unified-identity.ts"
REQUIREMENTS = (
    ROOT
    / "docs/a1/evidence/round54_identity_http_boundary_test_requirements.json"
)

ACTIVE = "active"
NON_ROUTABLE = {"proposed", "non_routable", "unavailable"}
DOMESTIC_QUALIFICATION_PROVIDERS = {"wechat", "qq", "alipay"}


def _go_manifest_routes() -> set[tuple[str, str]]:
    source = GO_SERVER.read_text(encoding="utf-8")
    match = re.search(
        r"func GoRouteManifestEntries\(\) \[\]RouteManifestEntry \{"
        r"(?P<body>.*?)"
        r"\n\}",
        source,
        re.DOTALL,
    )
    assert match, "GoRouteManifestEntries must remain statically inspectable"
    return {
        (method, path)
        for method, path in re.findall(
            r'go(?:Public|Scoped)Route\("([A-Z]+)",\s*"([^"]+)"',
            match.group("body"),
        )
    }


def _contract() -> dict[str, Any]:
    contract = a3_identity_contract_manifest()
    assert isinstance(contract, dict)
    return contract


def _routes_by_operation(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    routes = contract.get("routes")
    assert isinstance(routes, list) and routes, "A3 identity routes must be declared"
    indexed = {route["operation"]: route for route in routes}
    assert len(indexed) == len(routes), "identity route operations must be unique"
    return indexed


def _route_lifecycle(route: dict[str, Any]) -> str:
    lifecycle = route.get("lifecycle")
    assert lifecycle in {ACTIVE, *NON_ROUTABLE}, (
        f"{route.get('operation')} must declare lifecycle as active, proposed, "
        "non_routable, or unavailable; an omitted lifecycle must never imply active"
    )
    return lifecycle


def _typescript_routes() -> dict[str, dict[str, Any]]:
    source = TS_IDENTITY.read_text(encoding="utf-8")
    matches = re.findall(
        r'route\("([^"]+)",\s*"([A-Z]+)",\s*"([^"]+)",\s*'
        r'"(active|proposed|non_routable|unavailable)"\)',
        source,
    )
    return {
        operation: {
            "operation": operation,
            "method": method,
            "path": path,
            "lifecycle": lifecycle,
            "client_callable": lifecycle == ACTIVE,
        }
        for operation, method, path, lifecycle in matches
    }


def test_active_client_routes_are_backed_by_go_manifest() -> None:
    routes = _routes_by_operation(_contract())
    go_routes = _go_manifest_routes()

    for operation, route in routes.items():
        lifecycle = _route_lifecycle(route)
        route_key = (route["method"], route["path"])
        if lifecycle == ACTIVE:
            assert route_key in go_routes, (
                f"{operation} is advertised active but {route_key!r} is absent "
                "from GoRouteManifestEntries"
            )


def test_non_routable_routes_are_not_exposed_as_active_client_capabilities() -> None:
    routes = _routes_by_operation(_contract())
    go_routes = _go_manifest_routes()

    for operation, route in routes.items():
        lifecycle = _route_lifecycle(route)
        route_key = (route["method"], route["path"])
        if lifecycle in NON_ROUTABLE:
            assert route_key not in go_routes, (
                f"{operation} is {lifecycle} but Go advertises it as routable"
            )
            assert route.get("client_callable", False) is False, (
                f"{operation} is {lifecycle} and must not be callable by clients"
            )


def test_python_and_typescript_route_manifests_are_equal() -> None:
    python_routes = _routes_by_operation(_contract())
    typescript_routes = _typescript_routes()

    assert typescript_routes, (
        "TypeScript identity routes must declare operation, method, path, "
        "lifecycle, and client_callable"
    )
    assert typescript_routes == python_routes


def test_every_route_explicitly_declares_client_callability() -> None:
    for operation, route in _routes_by_operation(_contract()).items():
        assert isinstance(route.get("client_callable"), bool), (
            f"{operation} must explicitly declare client_callable"
        )
        lifecycle = _route_lifecycle(route)
        assert route["client_callable"] is (lifecycle == ACTIVE)


def test_registration_and_login_have_distinct_routes_and_authority() -> None:
    contract = _contract()
    routes = _routes_by_operation(contract)

    assert routes["register_start"]["path"] != routes["login_start"]["path"]
    assert routes["register_complete"]["path"] != routes["login_complete"]["path"]
    assert contract["registration"]["may_create_account"] is True
    assert contract["registration"]["verified_provider_proof_required"] is True
    assert contract["login"]["may_create_account"] is False
    assert contract["login"]["may_link_credentials"] is False
    assert contract["login"]["may_merge_accounts"] is False
    assert contract["login"]["existing_verified_credential_required"] is True


@pytest.mark.parametrize("provider", sorted(DOMESTIC_QUALIFICATION_PROVIDERS))
def test_domestic_identity_providers_fail_closed(provider: str) -> None:
    contract = _contract()
    providers = {item["provider"]: item for item in contract["providers"]}
    status = providers[provider]

    assert status["requires_business_qualification"] is True
    assert status["registration"] == "unavailable"
    assert status["login"] == "unavailable"
    assert status["linking"] == "unavailable"
    assert status.get("enabled", False) is False
    assert status.get("client_callable", False) is False


def test_public_login_failure_contract_is_anti_enumerating() -> None:
    login = _contract()["login"]

    assert login["unknown_identity_status"] == "failed"
    assert login["may_create_account"] is False
    assert login["may_link_credentials"] is False
    assert login["may_merge_accounts"] is False
    assert login.get("public_failure_code") == "authentication_failed"
    assert login.get("public_failure_http_status") in {400, 401}
    assert login.get("account_enumeration_safe") is True
    assert login.get("unknown_and_invalid_secret_share_public_failure") is True
    assert login.get("unknown_identity_next_action") not in {
        "register",
        "create_account",
        "link_account",
        "merge_account",
    }


def test_public_safe_requirements_fixture_matches_executable_checks() -> None:
    fixture = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))

    assert fixture["schema_version"] == "releasefoundry.round54.identity_http_test_requirements.v1"
    assert fixture["public_safe"] is True
    assert fixture["contains_secrets"] is False
    assert fixture["required_route_lifecycles"] == [
        "active",
        "proposed",
        "non_routable",
        "unavailable",
    ]
    assert set(fixture["domestic_fail_closed_providers"]) == (
        DOMESTIC_QUALIFICATION_PROVIDERS
    )
    assert fixture["registration_login_separation"]["login_may_create_account"] is False
    assert fixture["anti_enumeration"]["public_failure_code"] == "authentication_failed"
    assert fixture["anti_enumeration"]["same_failure_for_unknown_and_bad_secret"] is True
    assert fixture["oauth_first_registration"]["canonical_email_source"] == (
        "provider_verified_email_only"
    )
    assert fixture["oauth_first_registration"]["password_status"] == "absent"
    assert fixture["account_mutation_authorization"][
        "matching_authenticated_actor_required"
    ] is True
    assert fixture["account_mutation_authorization"][
        "recent_reauthentication_required"
    ] is True
    assert fixture["account_mutation_authorization"]["csrf_required"] is True
    assert fixture["two_factor"] == {
        "optional": True,
        "recommended": True,
        "mutation_requires_recent_reauthentication": True,
        "mutation_requires_csrf": True,
    }
