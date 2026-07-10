from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.parse import urlparse

import pytest

from ashr_clone.unified_identity import (
    IDENTITY_VERIFICATION_PROVIDERS,
    IDENTITY_VERIFICATION_PURPOSES,
    IdentityVerificationChallenge,
    IdentityVerificationReceipt,
    UnifiedIdentityClient,
    UnifiedIdentityContractError,
    identity_verification_challenge_route,
    identity_verification_challenges_route,
    identity_verification_resend_route,
    identity_verification_verify_route,
    unified_identity_contract_manifest,
)


NOW = "2026-07-10T10:00:00Z"
LATER = "2026-07-10T10:05:00Z"
COOLDOWN = "2026-07-10T10:01:00Z"


def _hint(provider: str) -> str:
    return "u***@example.invalid" if provider == "email" else "+86 138****8000"


def _challenge(provider: str = "email", purpose: str = "login", **overrides: Any) -> dict[str, Any]:
    payload = {
        "challenge_id": "challenge_01",
        "provider": provider,
        "purpose": purpose,
        "status": "pending",
        "destination_hint": _hint(provider),
        "destination_digest_ref": "digest-ref:destination/01",
        "created_at": NOW,
        "expires_at": LATER,
        "ttl_seconds": 300,
        "attempt_cap": 5,
        "attempts_remaining": 5,
        "resend_cooldown_seconds": 60,
        "resend_available_at": COOLDOWN,
        "single_use": True,
        "account_id": None if purpose == "login" else "acct_01",
        "verified_at": None,
        "consumed_at": None,
    }
    payload.update(overrides)
    return payload


def _receipt(provider: str = "email", purpose: str = "login", **overrides: Any) -> dict[str, Any]:
    payload = {
        "receipt_id": "receipt_01",
        "challenge_id": "challenge_01",
        "provider": provider,
        "purpose": purpose,
        "status": "verified",
        "destination_digest_ref": "digest-ref:destination/01",
        "verified_at": NOW,
        "expires_at": LATER,
        "single_use": True,
        "account_id": None if purpose == "login" else "acct_01",
        "consumed_at": None,
    }
    payload.update(overrides)
    return payload


def test_manifest_declares_provider_neutral_single_use_verification_contract() -> None:
    manifest = unified_identity_contract_manifest()
    assert manifest["verification"] == {
        "providers": ["email", "phone"],
        "purposes": ["binding", "login", "recovery"],
        "challenge_statuses": ["pending", "verified", "consumed", "expired", "locked"],
        "receipt_statuses": ["verified", "consumed", "expired"],
        "destination_input": "opaque_reference_only",
        "code_input": "opaque_reference_only",
        "ttl_required": True,
        "attempt_cap_required": True,
        "resend_cooldown_required": True,
        "single_use_required": True,
    }
    assert manifest["invariants"]["verification_login_does_not_merge_by_destination"] is True


@pytest.mark.parametrize("provider", IDENTITY_VERIFICATION_PROVIDERS)
@pytest.mark.parametrize("purpose", IDENTITY_VERIFICATION_PURPOSES)
def test_challenge_parity_for_every_provider_and_purpose(provider: str, purpose: str) -> None:
    challenge = IdentityVerificationChallenge.from_public_response(
        _challenge(provider, purpose)
    )
    assert challenge.provider == provider
    assert challenge.purpose == purpose
    assert challenge.ttl_seconds == 300
    assert challenge.attempt_cap == 5
    assert challenge.resend_cooldown_seconds == 60
    assert challenge.single_use is True
    assert "*" in challenge.destination_hint
    assert challenge.destination_digest_ref == "digest-ref:destination/01"


@pytest.mark.parametrize("provider", IDENTITY_VERIFICATION_PROVIDERS)
@pytest.mark.parametrize("purpose", IDENTITY_VERIFICATION_PURPOSES)
def test_receipt_parity_for_every_provider_and_purpose(provider: str, purpose: str) -> None:
    receipt = IdentityVerificationReceipt.from_public_response(
        _receipt(provider, purpose)
    )
    assert receipt.provider == provider
    assert receipt.purpose == purpose
    assert receipt.status == "verified"
    assert receipt.single_use is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"ttl_seconds": 0}, "ttl_seconds"),
        ({"attempt_cap": 0}, "attempt_cap"),
        ({"attempts_remaining": 6}, "cannot exceed"),
        ({"resend_cooldown_seconds": 0}, "resend_cooldown_seconds"),
        ({"single_use": False}, "single-use"),
        ({"status": "verified", "verified_at": None}, "verified_at"),
        ({"status": "consumed", "consumed_at": None}, "consumed_at"),
    ],
)
def test_challenge_rejects_invalid_lifecycle_controls(
    overrides: Mapping[str, Any], message: str
) -> None:
    with pytest.raises(UnifiedIdentityContractError, match=message):
        IdentityVerificationChallenge.from_public_response(_challenge(**overrides))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"single_use": False}, "single-use"),
        ({"status": "consumed", "consumed_at": None}, "consumed_at"),
        ({"destination_digest_ref": "sha256:" + "a" * 64}, "opaque"),
    ],
)
def test_receipt_rejects_replay_unsafe_or_digest_value_shapes(
    overrides: Mapping[str, Any], message: str
) -> None:
    with pytest.raises(UnifiedIdentityContractError, match=message):
        IdentityVerificationReceipt.from_public_response(_receipt(**overrides))


@pytest.mark.parametrize(
    "field",
    [
        "email",
        "email_address",
        "phone",
        "phone_number",
        "otp",
        "verification_code",
        "verification_value",
        "destination",
        "destination_value",
        "password",
        "client_secret",
        "access_token",
    ],
)
def test_verification_dtos_recursively_reject_sensitive_fields(field: str) -> None:
    with pytest.raises(UnifiedIdentityContractError, match="must not include"):
        IdentityVerificationChallenge.from_public_response(
            _challenge(metadata={"nested": [{"private": {field: "secret"}}]})
        )


def test_login_challenges_with_same_hint_never_imply_account_merge() -> None:
    first = IdentityVerificationChallenge.from_public_response(
        _challenge(challenge_id="challenge_first")
    )
    second = IdentityVerificationChallenge.from_public_response(
        _challenge(challenge_id="challenge_second")
    )
    assert first.destination_hint == second.destination_hint
    assert first.account_id is None
    assert second.account_id is None
    assert "merge" not in json.dumps(first.to_dict()).lower()
    assert first.challenge_id != second.challenge_id


def test_binding_and_recovery_require_explicit_account_but_login_does_not() -> None:
    client = UnifiedIdentityClient("http://localhost:8787", transport=lambda *_: {})
    for purpose in ("binding", "recovery"):
        with pytest.raises(UnifiedIdentityContractError, match="requires account_id"):
            client.start_verification(
                "email",
                purpose,
                destination_ref="vault-ref:destination/01",
                idempotency_key=f"idem_{purpose}",
            )


def test_verification_http_client_routes_and_opaque_reference_payloads() -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def transport(method: str, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        path = urlparse(url).path
        calls.append((method, path, dict(payload)))
        if path.endswith("/resend"):
            return _challenge("phone", "binding", account_id="acct_01")
        if path.endswith("/verify"):
            return _receipt("phone", "binding", account_id="acct_01")
        if path == "/v1/identity/verifications/challenges":
            return _challenge("phone", "binding", account_id="acct_01")
        return _challenge("phone", "binding", account_id="acct_01")

    client = UnifiedIdentityClient("http://localhost:8787/", transport=transport)
    started = client.start_verification(
        "phone",
        "binding",
        destination_ref="vault-ref:destination/phone-01",
        account_id="acct_01",
        idempotency_key="idem_start",
    )
    fetched = client.get_verification("challenge /01")
    resent = client.resend_verification("challenge_01", idempotency_key="idem_resend")
    receipt = client.verify_challenge(
        "challenge_01",
        verification_code_ref="vault-ref:otp/code-01",
        idempotency_key="idem_verify",
    )

    assert started.provider == fetched.provider == resent.provider == receipt.provider == "phone"
    assert calls == [
        (
            "POST",
            "/v1/identity/verifications/challenges",
            {
                "provider": "phone",
                "purpose": "binding",
                "destination_ref": "vault-ref:destination/phone-01",
                "idempotency_key": "idem_start",
                "account_id": "acct_01",
            },
        ),
        ("GET", "/v1/identity/verifications/challenges/challenge%20%2F01", {}),
        (
            "POST",
            "/v1/identity/verifications/challenges/challenge_01/resend",
            {"idempotency_key": "idem_resend"},
        ),
        (
            "POST",
            "/v1/identity/verifications/challenges/challenge_01/verify",
            {
                "verification_code_ref": "vault-ref:otp/code-01",
                "idempotency_key": "idem_verify",
            },
        ),
    ]


@pytest.mark.parametrize(
    ("provider", "purpose"),
    [
        ("github", "login"),
        ("google", "binding"),
        ("email", "signup"),
        ("phone", "reset"),
    ],
)
def test_client_rejects_unsupported_provider_or_purpose_before_transport(
    provider: str, purpose: str
) -> None:
    calls: list[object] = []
    client = UnifiedIdentityClient(
        "http://localhost:8787", transport=lambda *args: calls.append(args) or {}
    )
    with pytest.raises(UnifiedIdentityContractError):
        client.start_verification(
            provider,
            purpose,
            destination_ref="vault-ref:destination/01",
            account_id="acct_01",
            idempotency_key="idem",
        )
    assert calls == []


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("destination_ref", "user@example.invalid"),
        ("destination_ref", "tel:+8613812348000"),
        ("verification_code_ref", "123456"),
        ("verification_code_ref", "mailto:user@example.invalid"),
    ],
)
def test_client_rejects_raw_destination_and_code_material_before_transport(
    argument: str, value: str
) -> None:
    calls: list[object] = []
    client = UnifiedIdentityClient(
        "http://localhost:8787", transport=lambda *args: calls.append(args) or {}
    )
    with pytest.raises(UnifiedIdentityContractError):
        if argument == "destination_ref":
            client.start_verification(
                "email",
                "login",
                destination_ref=value,
                idempotency_key="idem",
            )
        else:
            client.verify_challenge(
                "challenge_01",
                verification_code_ref=value,
                idempotency_key="idem",
            )
    assert calls == []


def test_verification_route_helpers_are_stable_and_encode_ids() -> None:
    assert identity_verification_challenges_route() == "/v1/identity/verifications/challenges"
    assert identity_verification_challenge_route("challenge /01").endswith(
        "/challenge%20%2F01"
    )
    assert identity_verification_resend_route("challenge_01").endswith(
        "/challenge_01/resend"
    )
    assert identity_verification_verify_route("challenge_01").endswith(
        "/challenge_01/verify"
    )


def test_public_guard_allows_only_safe_error_destination_descriptions() -> None:
    IdentityVerificationChallenge.from_public_response(
        _challenge(
            error={
                "code": "identity_verification_failed",
                "details": {"destination": "verification provider"},
            }
        )
    )
    for destination in ("user@example.invalid", "+8613812348000"):
        with pytest.raises(UnifiedIdentityContractError):
            IdentityVerificationChallenge.from_public_response(
                _challenge(
                    error={
                        "code": "identity_verification_failed",
                        "details": {"destination": destination},
                    }
                )
            )
