from __future__ import annotations

import pytest

from releasefoundry.unified_identity import (
    IdentityLoginCompleteRequest,
    IdentityLoginStartRequest,
    IdentityRegistrationCompleteRequest,
    IdentityRegistrationStartRequest,
    UnifiedIdentityContractError,
    a3_identity_contract_manifest,
)


SCOPE = {"tenant_id": "tenant_contract", "project_id": "project_contract"}


def test_route_lifecycle_is_explicit_and_fail_closed() -> None:
    manifest = a3_identity_contract_manifest()
    routes = {
        route["operation"]: route
        for route in manifest["routes"]
    }
    for route in routes.values():
        assert route["lifecycle"] in {
            "active",
            "proposed",
            "non_routable",
            "unavailable",
        }
        assert route["client_callable"] is (route["lifecycle"] == "active")

    for operation in {
        "link_start",
        "link_complete",
        "unlink",
    }:
        assert routes[operation]["lifecycle"] == "proposed"
        assert routes[operation]["client_callable"] is False

    for operation in {
        "security_posture",
        "password_set",
        "password_change",
        "password_recover",
        "two_factor_enroll",
        "two_factor_verify",
        "two_factor_recovery_consume",
        "two_factor_recovery_rotate",
        "two_factor_disable",
    }:
        assert routes[operation]["lifecycle"] == "active"
        assert routes[operation]["client_callable"] is True

    providers = {item["provider"]: item for item in manifest["providers"]}
    for provider in {"email", "github", "google"}:
        assert providers[provider]["registration"] == "available"
        assert providers[provider]["login"] == "available"
        assert providers[provider]["linking"] == "proposed"
    for provider in {"wechat", "qq", "alipay", "phone"}:
        assert providers[provider]["linking"] == "unavailable"


def test_registration_and_login_dtos_are_distinct_and_receipt_driven() -> None:
    assert IdentityRegistrationStartRequest.from_public_request(
        {**SCOPE, "provider": "email"}
    ).to_dict() == {**SCOPE, "provider": "email"}
    assert IdentityLoginStartRequest.from_public_request(
        {**SCOPE, "provider": "github"}
    ).to_dict() == {**SCOPE, "provider": "github"}
    assert IdentityRegistrationCompleteRequest.from_public_request(
        {**SCOPE, "proof_receipt_id": "receipt_register"}
    ).to_dict() == {**SCOPE, "proof_receipt_id": "receipt_register"}
    assert IdentityLoginCompleteRequest.from_public_request(
        {**SCOPE, "proof_receipt_id": "receipt_login"}
    ).to_dict() == {**SCOPE, "proof_receipt_id": "receipt_login"}


@pytest.mark.parametrize(
    "dto,payload",
    [
        (
            IdentityRegistrationStartRequest,
            {**SCOPE, "provider": "email", "verified": True},
        ),
        (
            IdentityRegistrationCompleteRequest,
            {**SCOPE, "proof_receipt_id": "receipt_register", "is_verified": True},
        ),
        (
            IdentityLoginStartRequest,
            {**SCOPE, "provider": "email", "verification_status": "verified"},
        ),
        (
            IdentityLoginCompleteRequest,
            {**SCOPE, "proof_receipt_id": "receipt_login", "verified": True},
        ),
    ],
)
def test_public_flow_dto_rejects_caller_asserted_verification(
    dto: type, payload: dict[str, object]
) -> None:
    with pytest.raises(UnifiedIdentityContractError):
        dto.from_public_request(payload)


def test_login_failure_contract_is_stable_and_anti_enumerating() -> None:
    login = a3_identity_contract_manifest()["login"]
    assert login["public_failure_code"] == "authentication_failed"
    assert login["public_failure_http_status"] == 401
    assert login["account_enumeration_safe"] is True
    assert login["unknown_and_invalid_secret_share_public_failure"] is True
    assert login["unknown_identity_next_action"] is None
