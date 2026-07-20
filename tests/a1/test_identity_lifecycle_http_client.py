from __future__ import annotations

import pytest

from ashr_clone.unified_identity import (
    A3_IDENTITY_CONTRACT_SCHEMA_VERSION,
    IdentityLifecycleHTTPClient,
    IdentityLifecycleHTTPError,
    IdentityLifecycleHTTPResponse,
    IdentityLifecycleTransportError,
    IdentityLoginCompleteRequest,
    IdentityLoginStartRequest,
    IdentityRegistrationCompleteRequest,
    IdentityRegistrationStartRequest,
)


SCOPE = {"tenant_id": "tenant_sdk", "project_id": "project_sdk"}


def _security(*, enumeration_safe: bool) -> dict[str, bool]:
    return {
        "server_verified_proof_required": True,
        "recent_reauthentication_required": False,
        "csrf_required": False,
        "account_enumeration_safe": enumeration_safe,
    }


def _envelope(
    operation: str,
    status: str,
    *,
    provider: str = "email",
    account: dict[str, object] | None = None,
    error: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": A3_IDENTITY_CONTRACT_SCHEMA_VERSION,
        "operation": operation,
        "status": status,
        "provider": provider,
        "account": account,
        "next_action": "none" if status == "failed" else "complete_provider",
        "security": _security(enumeration_safe=operation.startswith("login")),
    }
    if error is not None:
        payload["error"] = error
    return payload


def _account() -> dict[str, object]:
    return {
        "account_id": "account_sdk",
        "password_status": "absent",
        "two_factor": {
            "status": "disabled",
            "optional": True,
            "recommended": True,
        },
    }


def test_typed_registration_and_login_requests_remain_distinct() -> None:
    calls: list[tuple[str, str, dict[str, object], float]] = []
    responses = iter(
        [
            IdentityLifecycleHTTPResponse(
                201,
                {
                    **_envelope("register_start", "verification_required"),
                    "receipt_id": "ipr_registration",
                    "expires_at": "2026-07-12T12:00:00Z",
                },
            ),
            IdentityLifecycleHTTPResponse(
                201,
                {
                    **_envelope(
                        "register_complete", "completed", account=_account()
                    ),
                    "next_action": "enroll_two_factor",
                },
            ),
            IdentityLifecycleHTTPResponse(
                201,
                {
                    **_envelope("login_start", "verification_required"),
                    "receipt_id": "ipr_login",
                    "expires_at": "2026-07-12T12:00:00Z",
                },
            ),
            IdentityLifecycleHTTPResponse(
                200,
                {
                    **_envelope("login_complete", "authenticated", account=_account()),
                    "authenticated_at": "2026-07-12T11:55:00Z",
                },
            ),
        ]
    )

    def transport(method: str, url: str, body: dict, timeout: float):
        calls.append((method, url, body, timeout))
        return next(responses)

    client = IdentityLifecycleHTTPClient(
        "http://localhost:8787", transport=transport, timeout_seconds=4
    )
    assert client.registration_start(
        IdentityRegistrationStartRequest.from_public_request(
            {**SCOPE, "provider": "email"}
        )
    ).receipt_id == "ipr_registration"
    assert client.registration_complete(
        IdentityRegistrationCompleteRequest.from_public_request(
            {**SCOPE, "proof_receipt_id": "ipr_registration"}
        )
    ).account.account_id == "account_sdk"
    assert client.login_start(
        IdentityLoginStartRequest.from_public_request(
            {**SCOPE, "provider": "email"}
        )
    ).receipt_id == "ipr_login"
    assert client.login_complete(
        IdentityLoginCompleteRequest.from_public_request(
            {**SCOPE, "proof_receipt_id": "ipr_login"}
        )
    ).status == "authenticated"

    assert [call[1].removeprefix("http://localhost:8787") for call in calls] == [
        "/v1/identity/registration/start",
        "/v1/identity/registration/complete",
        "/v1/identity/login/start",
        "/v1/identity/login/complete",
    ]
    assert calls[1][2] == {**SCOPE, "receipt_id": "ipr_registration"}
    assert calls[3][2] == {**SCOPE, "receipt_id": "ipr_login"}
    for _, _, body, timeout in calls:
        assert timeout == 4
        assert not {
            "account_id",
            "credential_id",
            "verified_email",
            "bind",
            "merge",
            "create_account",
        }.intersection(body)


def test_login_failure_is_structured_public_safe_and_anti_enumerating() -> None:
    def transport(*_args):
        return IdentityLifecycleHTTPResponse(
            401,
            _envelope(
                "login_complete",
                "failed",
                error={
                    "code": "authentication_failed",
                    "http_status": 401,
                    "anti_enumeration": True,
                    "retryable": False,
                    "public_safe": True,
                },
            ),
        )

    client = IdentityLifecycleHTTPClient("http://localhost:8787", transport=transport)
    with pytest.raises(IdentityLifecycleHTTPError) as raised:
        client.login_complete(
            IdentityLoginCompleteRequest.from_public_request(
                {**SCOPE, "proof_receipt_id": "ipr_unknown_or_invalid"}
            )
        )
    assert raised.value.code == "authentication_failed"
    assert raised.value.http_status == 401
    assert raised.value.anti_enumeration is True
    assert raised.value.public_safe is True
    assert "unknown" not in str(raised.value)
    assert "account" not in str(raised.value)


def test_capability_get_retries_but_lifecycle_writes_never_retry() -> None:
    capability_attempts = 0

    def capability_transport(*_args):
        nonlocal capability_attempts
        capability_attempts += 1
        if capability_attempts < 3:
            raise TimeoutError
        return IdentityLifecycleHTTPResponse(
            200,
            {
                "schema_version": "ashr.clone.a3_identity.providers.v1",
                "providers": [],
            },
        )

    client = IdentityLifecycleHTTPClient(
        "http://localhost:8787",
        transport=capability_transport,
        max_retries=2,
        retry_backoff_seconds=0,
    )
    assert client.provider_capabilities().providers == ()
    assert capability_attempts == 3

    write_attempts = 0

    def write_transport(*_args):
        nonlocal write_attempts
        write_attempts += 1
        raise TimeoutError

    client = IdentityLifecycleHTTPClient(
        "http://localhost:8787",
        transport=write_transport,
        max_retries=10,
        retry_backoff_seconds=0,
    )
    with pytest.raises(IdentityLifecycleTransportError) as raised:
        client.login_start(
            IdentityLoginStartRequest.from_public_request(
                {**SCOPE, "provider": "github"}
            )
        )
    assert write_attempts == 1
    assert raised.value.retryable is False


def test_provider_capabilities_preserve_three_readiness_dimensions() -> None:
    def transport(*_args):
        return IdentityLifecycleHTTPResponse(
            200,
            {
                "schema_version": "ashr.clone.a3_identity.providers.v1",
                "providers": [
                    {
                        "provider": "wechat",
                        "preferred": False,
                        "enabled": False,
                        "code_capability": "adapter_only",
                        "deployment_readiness": "blocked",
                        "deployment_status_source": "business_qualification",
                        "environment": "development",
                        "qualification_status": "required",
                        "requires_business_qualification": True,
                        "reason_code": "business_qualification_required",
                        "registration_status": "unavailable",
                        "login_status": "unavailable",
                        "linking_status": "unavailable",
                    }
                ],
            },
        )

    capabilities = IdentityLifecycleHTTPClient(
        "http://localhost:8787", transport=transport
    ).provider_capabilities()
    wechat = capabilities.providers[0]
    assert wechat.code_capability == "adapter_only"
    assert wechat.deployment_readiness == "blocked"
    assert wechat.qualification_status == "required"
    assert wechat.registration_status == "unavailable"
    assert wechat.login_status == "unavailable"
