from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.parse import urlparse

import pytest

from ashr_clone.unified_identity import (
    IDENTITY_SECURITY_HTTP_SCHEMA_VERSION,
    IDENTITY_SECURITY_SERVICE_SCHEMA_VERSION,
    UNIFIED_IDENTITY_ERROR_CODES,
    UNIFIED_IDENTITY_PROVIDERS,
    IdentityCredential,
    IdentityMerge,
    IdentityRecovery,
    IdentitySecurityBeginResult,
    IdentitySecurityConfirmResult,
    IdentitySecurityPosture,
    UnifiedAccount,
    UnifiedIdentityClient,
    UnifiedIdentityContractError,
    UnifiedIdentityError,
    identity_password_begin_route,
    identity_link_route,
    identity_two_factor_enroll_begin_route,
    identity_two_factor_enroll_confirm_route,
    identity_two_factor_route,
    unified_identity_contract_manifest,
)


NOW = "2026-07-10T10:00:00Z"


def _credential(provider: str = "google", **overrides: Any) -> dict[str, Any]:
    payload = {
        "credential_id": f"cred_{provider}",
        "account_id": "acct_canonical",
        "provider": provider,
        "provider_subject_present": True,
        "status": "active",
        "verified": True,
        "display_hint": "verified-user" if provider not in {"phone", "email"} else (
            "+86 138****8000" if provider == "phone" else "u***@example.invalid"
        ),
        "linked_at": NOW,
        "last_used_at": NOW,
        "revoked_at": None,
    }
    payload.update(overrides)
    return payload


def _membership(**overrides: Any) -> dict[str, Any]:
    payload = {
        "membership_id": "mem_owner",
        "account_id": "acct_canonical",
        "tenant_id": "tenant_cn",
        "project_id": "project_main",
        "role": "owner",
        "status": "active",
        "joined_at": NOW,
    }
    payload.update(overrides)
    return payload


def _account(**overrides: Any) -> dict[str, Any]:
    payload = {
        "schema_version": "ashr.clone.unified_identity.v1",
        "account_id": "acct_canonical",
        "status": "active",
        "display_name": "Ashr User",
        "created_at": NOW,
        "updated_at": NOW,
        "merged_into_account_id": None,
        "credentials": [_credential()],
        "memberships": [_membership()],
    }
    payload.update(overrides)
    return payload


def test_manifest_models_all_login_methods_as_credentials_of_one_account() -> None:
    manifest = unified_identity_contract_manifest()

    assert UNIFIED_IDENTITY_PROVIDERS == (
        "github",
        "google",
        "wechat",
        "qq",
        "alipay",
        "phone",
        "email",
    )
    assert manifest["subject_model"] == "one_account_many_credentials"
    assert manifest["invariants"]["email_match_does_not_merge_accounts"] is True
    assert manifest["invariants"]["memberships_attach_to_canonical_account"] is True
    assert manifest["invariants"]["merge_repoints_credentials_atomically"] is True
    assert manifest["public_safety"] == {
        "raw_email_present": False,
        "raw_phone_present": False,
        "raw_password_present": False,
        "raw_otp_present": False,
        "oauth_code_present": False,
        "oauth_token_present": False,
        "provider_secret_present": False,
        "provider_subject_digest_present": False,
        "provider_subject_presence_marker_only": True,
    }
    assert {
        "identity_credential_conflict",
        "identity_last_credential_unlink_forbidden",
        "identity_merge_requires_step_up",
        "identity_recovery_rate_limited",
    }.issubset(UNIFIED_IDENTITY_ERROR_CODES)


@pytest.mark.parametrize("provider", UNIFIED_IDENTITY_PROVIDERS)
def test_all_providers_share_the_same_public_credential_shape(provider: str) -> None:
    credential = IdentityCredential.from_public_response(_credential(provider))

    assert credential.account_id == "acct_canonical"
    assert credential.provider == provider
    assert credential.provider_subject_present is True
    serialized = json.dumps(credential.to_dict())
    assert "provider_subject_sha256" not in serialized
    assert "subject_digest" not in serialized
    assert "identifier_sha256" not in serialized
    assert "token" not in serialized
    assert "secret" not in serialized


def test_account_owns_credentials_and_memberships_with_matching_account_ids() -> None:
    account = UnifiedAccount.from_public_response(
        _account(
            credentials=[_credential("github"), _credential("phone"), _credential("email")],
            memberships=[_membership(), _membership(membership_id="mem_dev", role="developer")],
        )
    )

    assert account.account_id == "acct_canonical"
    assert [item.provider for item in account.credentials] == ["github", "phone", "email"]
    assert len(account.memberships) == 2

    with pytest.raises(UnifiedIdentityContractError, match="account mismatch"):
        UnifiedAccount.from_public_response(
            _account(credentials=[_credential(account_id="acct_other")])
        )


def test_account_dto_is_isolated_from_recursive_input_and_output_mutation() -> None:
    payload = _account(
        credentials=[_credential("github")],
        memberships=[_membership()],
        metadata={"safe": [{"label": "original"}]},
    )
    account = UnifiedAccount.from_public_response(payload)

    payload["credentials"][0]["provider"] = "google"
    payload["memberships"][0]["role"] = "viewer"
    payload["metadata"]["safe"][0]["label"] = "mutated"
    exported = account.to_dict()
    exported["credentials"][0]["provider"] = "wechat"
    exported["memberships"][0]["role"] = "billing"

    assert account.credentials[0].provider == "github"
    assert account.memberships[0].role == "owner"
    assert account.to_dict()["credentials"][0]["provider"] == "github"
    assert account.to_dict()["memberships"][0]["role"] == "owner"
    assert "metadata" not in account.to_dict()


@pytest.mark.parametrize(
    ("provider", "display_hint"),
    [
        ("phone", "+86 138****8000"),
        ("email", "u***@example.invalid"),
    ],
)
def test_matching_phone_or_email_hint_never_implicitly_merges_accounts(
    provider: str, display_hint: str
) -> None:
    first = UnifiedAccount.from_public_response(
        _account(
            account_id="acct_first",
            credentials=[
                _credential(
                    provider,
                    credential_id=f"cred_{provider}_first",
                    account_id="acct_first",
                    display_hint=display_hint,
                )
            ],
            memberships=[_membership(account_id="acct_first")],
        )
    )
    second = UnifiedAccount.from_public_response(
        _account(
            account_id="acct_second",
            credentials=[
                _credential(
                    provider,
                    credential_id=f"cred_{provider}_second",
                    account_id="acct_second",
                    display_hint=display_hint,
                )
            ],
            memberships=[_membership(account_id="acct_second")],
        )
    )

    assert first.account_id == "acct_first"
    assert second.account_id == "acct_second"
    assert first.account_id != second.account_id
    assert first.credentials[0].credential_id != second.credentials[0].credential_id


@pytest.mark.parametrize(
    "field",
    [
        "access_token",
        "authorization_code",
        "client_secret",
        "code_verifier",
        "id_token",
        "otp",
        "password",
        "phone",
        "email",
        "refresh_token",
        "state",
    ],
)
def test_public_dtos_reject_raw_secret_and_identity_fields_recursively(field: str) -> None:
    payload = _account(metadata={"nested": {field: "must-not-cross-sdk-boundary"}})
    with pytest.raises(UnifiedIdentityContractError, match=field):
        UnifiedAccount.from_public_response(payload)


def test_phone_and_email_require_masked_hints_and_subject_presence_only() -> None:
    assert IdentityCredential.from_public_response(
        _credential("phone", display_hint="+86 138****8000")
    ).display_hint == "+86 138****8000"
    assert IdentityCredential.from_public_response(
        _credential("email", display_hint="u***@example.invalid")
    ).display_hint == "u***@example.invalid"

    with pytest.raises(UnifiedIdentityContractError, match="phone display hint"):
        IdentityCredential.from_public_response(
            _credential("phone", display_hint="+8613812348000")
        )
    with pytest.raises(UnifiedIdentityContractError, match="email display hint"):
        IdentityCredential.from_public_response(
            _credential("email", display_hint="unmasked")
        )


@pytest.mark.parametrize(
    "field",
    ["provider_subject_sha256", "subject_digest", "identifier_sha256"],
)
def test_public_dtos_reject_stable_provider_subject_digests(field: str) -> None:
    with pytest.raises(UnifiedIdentityContractError, match=field):
        IdentityCredential.from_public_response(
            _credential("wechat", **{field: "a" * 64})
        )


@pytest.mark.parametrize(
    "field",
    [
        "tokenRef",
        "tokenref",
        "tokenRefId",
        "token-ref-id",
        "revocationOutboxId",
        "revocationoutboxid",
    ],
)
def test_public_dtos_reject_normalized_sensitive_aliases(field: str) -> None:
    with pytest.raises(UnifiedIdentityContractError, match="must not include"):
        UnifiedAccount.from_public_response(
            _account(metadata={"nested": {field: "opaque-private-reference"}})
        )


def test_provider_subject_presence_marker_is_required_and_boolean() -> None:
    payload = _credential("qq")
    payload.pop("provider_subject_present")
    with pytest.raises(
        UnifiedIdentityContractError, match="provider_subject_present must be a boolean"
    ):
        IdentityCredential.from_public_response(payload)

    with pytest.raises(
        UnifiedIdentityContractError, match="provider_subject_present must be a boolean"
    ):
        IdentityCredential.from_public_response(
            _credential("qq", provider_subject_present="true")
        )


def test_merge_returns_one_canonical_account_and_repoint_counts() -> None:
    merge = IdentityMerge.from_public_response(
        {
            "merge_id": "merge_01",
            "canonical_account": _account(),
            "merged_account_ids": ["acct_google_legacy", "acct_phone_legacy"],
            "credentials_repointed": 3,
            "memberships_repointed": 2,
            "completed_at": NOW,
        }
    )

    assert merge.canonical_account.account_id == "acct_canonical"
    assert merge.merged_account_ids == ("acct_google_legacy", "acct_phone_legacy")
    assert merge.credentials_repointed == 3

    with pytest.raises(UnifiedIdentityContractError) as exc:
        IdentityMerge.from_public_response(
            {
                **merge.to_dict(),
                "merged_account_ids": ["acct_canonical"],
            }
        )
    assert exc.value.code == "identity_merge_cycle"


@pytest.mark.parametrize("provider", ["phone", "email"])
def test_recovery_exposes_only_masked_destination(provider: str) -> None:
    recovery = IdentityRecovery.from_public_response(
        {
            "recovery_id": "recovery_01",
            "account_id": "acct_canonical",
            "provider": provider,
            "destination_hint": (
                "+86 138****8000" if provider == "phone" else "u***@example.invalid"
            ),
            "status": "pending",
            "expires_at": NOW,
            "attempts_remaining": 4,
        }
    )
    assert "*" in recovery.destination_hint

    with pytest.raises(UnifiedIdentityContractError):
        IdentityRecovery.from_public_response(
            {**recovery.to_dict(), "otp": "123456"}
        )


def test_stable_error_contract_redacts_message_and_rejects_unknown_codes() -> None:
    error = UnifiedIdentityError.from_public_response(
        {
            "code": "identity_recovery_rate_limited",
            "message": "Contact user@example.invalid with Bearer abc.def.ghi",
            "retryable": True,
            "provider": "email",
            "retry_after_seconds": 60,
        }
    )
    assert error.code == "identity_recovery_rate_limited"
    assert error.retry_after_seconds == 60
    assert "user@example.invalid" not in error.message
    assert "abc.def.ghi" not in error.message

    with pytest.raises(UnifiedIdentityContractError, match="unknown"):
        UnifiedIdentityError.from_public_response(
            {"code": "provider_dumped_exception", "message": "unsafe"}
        )


def test_route_helpers_encode_ids_and_keep_provider_under_account_credentials() -> None:
    assert identity_link_route("acct with/slash", "wechat") == (
        "/v1/accounts/acct%20with%2Fslash/credentials/wechat/link"
    )


def test_security_route_helpers_only_emit_backed_begin_and_confirm_paths() -> None:
    assert identity_password_begin_route("acct_01", "set") == (
        "/v1/accounts/acct_01/password/enroll/begin"
    )
    assert identity_password_begin_route("acct_01", "change") == (
        "/v1/accounts/acct_01/password/change/begin"
    )
    assert identity_password_begin_route("acct_01", "recover") == (
        "/v1/accounts/acct_01/password/recover/begin"
    )
    assert identity_two_factor_enroll_begin_route("acct_01") == (
        "/v1/accounts/acct_01/two-factor/enroll/begin"
    )
    assert identity_two_factor_enroll_confirm_route("acct_01") == (
        "/v1/accounts/acct_01/two-factor/enroll/confirm"
    )
    assert identity_two_factor_route("acct_01", "verify").endswith("/enroll/confirm")
    with pytest.raises(UnifiedIdentityContractError):
        identity_two_factor_route("acct_01", "recovery")
    with pytest.raises(UnifiedIdentityContractError):
        identity_two_factor_route("acct_01", "disable")


def test_flat_identity_security_dtos_are_strict_and_public_safe() -> None:
    posture = IdentitySecurityPosture.from_public_response(
        {
            "schema_version": IDENTITY_SECURITY_HTTP_SCHEMA_VERSION,
            "password_status": "set",
            "password_change_available": True,
            "password_recovery_available": True,
            "two_factor_status": "disabled",
            "two_factor_optional": True,
            "two_factor_recommended": True,
            "recovery_codes_remaining": 0,
            "security_version": 4,
            "active_sessions": 2,
        }
    )
    assert posture.to_dict() == {
        "schema_version": IDENTITY_SECURITY_HTTP_SCHEMA_VERSION,
        "password_status": "set",
        "password_change_available": True,
        "password_recovery_available": True,
        "two_factor_status": "disabled",
        "two_factor_optional": True,
        "two_factor_recommended": True,
        "recovery_codes_remaining": 0,
        "security_version": 4,
        "active_sessions": 2,
    }

    begin = IdentitySecurityBeginResult.from_public_response(
        {
            "schema_version": IDENTITY_SECURITY_SERVICE_SCHEMA_VERSION,
            "operation": "mfa_enroll",
            "two_factor_status": "pending",
            "two_factor_optional": True,
            "two_factor_recommended": True,
            "confirmation_required": True,
            "confirmation_challenge_id": "challenge_a1_01",
            "provisioning_uri": "otpauth://totp/Ashr%3Atest",
            "security_version": 5,
            "sessions_revoked": 0,
        }
    )
    assert begin.challenge_id == "challenge_a1_01"
    assert "confirmation_challenge_id" not in begin.to_dict()
    assert begin.two_factor_optional is True
    assert begin.two_factor_recommended is True

    confirm = IdentitySecurityConfirmResult.from_public_response(
        {
            "schema_version": IDENTITY_SECURITY_SERVICE_SCHEMA_VERSION,
            "operation": "mfa_confirm",
            "two_factor_status": "enabled",
            "two_factor_optional": True,
            "two_factor_recommended": True,
            "recovery_codes": ["RECOVERY-A1-0001", "RECOVERY-A1-0002"],
            "recovery_codes_remaining": 2,
            "security_version": 6,
            "sessions_revoked": 1,
            "reauthentication_required": True,
        },
        challenge_id="challenge_a1_01",
    )
    assert confirm.challenge_id == "challenge_a1_01"
    assert confirm.recovery_codes == ("RECOVERY-A1-0001", "RECOVERY-A1-0002")
    assert "password" not in confirm.to_dict()
    assert "code" not in confirm.to_dict()

    with pytest.raises(UnifiedIdentityContractError, match="schema version"):
        IdentitySecurityPosture.from_public_response(
            {
                **posture.to_dict(),
                "schema_version": "ashr.identity_security_http.v0",
            }
        )
    with pytest.raises(UnifiedIdentityContractError, match="challenge"):
        IdentitySecurityBeginResult.from_public_response(
            {
                "schema_version": IDENTITY_SECURITY_SERVICE_SCHEMA_VERSION,
                "operation": "mfa_enroll",
                "two_factor_status": "pending",
                "two_factor_optional": True,
                "two_factor_recommended": True,
                "confirmation_required": True,
                "provisioning_uri": "otpauth://totp/Ashr%3Atest",
                "security_version": 5,
                "sessions_revoked": 0,
            }
        )


def test_security_client_uses_dedicated_sensitive_transports_and_secret_free_dtos() -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []
    password_value = "A1-only-test-password!"
    totp_value = "123456"

    def transport(method: str, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        path = urlparse(url).path
        calls.append((method, path, dict(payload)))
        if path.endswith("/security"):
            return {
                "schema_version": IDENTITY_SECURITY_HTTP_SCHEMA_VERSION,
                "password_status": "absent",
                "password_change_available": False,
                "password_recovery_available": True,
                "two_factor_status": "disabled",
                "two_factor_optional": True,
                "two_factor_recommended": True,
                "recovery_codes_remaining": 0,
                "security_version": 1,
                "active_sessions": 1,
            }
        if path.endswith("/password/enroll/begin"):
            return {
                "schema_version": IDENTITY_SECURITY_SERVICE_SCHEMA_VERSION,
                "operation": "password_enroll",
                "password_status": "set",
                "two_factor_optional": True,
                "two_factor_recommended": True,
                "security_version": 2,
                "sessions_revoked": 1,
                "reauthentication_required": True,
            }
        if path.endswith("/two-factor/enroll/begin"):
            return {
                "schema_version": IDENTITY_SECURITY_SERVICE_SCHEMA_VERSION,
                "operation": "mfa_enroll",
                "two_factor_status": "pending",
                "two_factor_optional": True,
                "two_factor_recommended": True,
                "confirmation_required": True,
                "confirmation_challenge_id": "challenge_a1_02",
                "provisioning_uri": "otpauth://totp/Ashr%3Atest",
                "security_version": 3,
                "sessions_revoked": 0,
            }
        if path.endswith("/two-factor/enroll/confirm"):
            return {
                "schema_version": IDENTITY_SECURITY_SERVICE_SCHEMA_VERSION,
                "operation": "mfa_confirm",
                "two_factor_status": "enabled",
                "two_factor_optional": True,
                "two_factor_recommended": True,
                "recovery_codes": ["RECOVERY-A1-1001", "RECOVERY-A1-1002"],
                "recovery_codes_remaining": 2,
                "security_version": 4,
                "sessions_revoked": 1,
                "reauthentication_required": True,
            }
        raise AssertionError(path)

    client = UnifiedIdentityClient("https://identity.example", transport=transport)
    assert client.get_security_posture("acct_01").two_factor_recommended is True
    password_result = client.begin_password_enroll(
        "acct_01",
        password_value,
        idempotency_key="idem-password-enroll-01",
    )
    begin_result = client.begin_two_factor_enroll(
        "acct_01",
        idempotency_key="idem-mfa-begin-01",
    )
    confirm_result = client.confirm_two_factor_enroll(
        "acct_01",
        begin_result.challenge_id or "",
        totp_value,
        idempotency_key="idem-mfa-confirm-01",
    )

    assert calls[1] == (
        "POST",
        "/v1/accounts/acct_01/password/enroll/begin",
        {
            "password": password_value,
            "idempotency_key": "idem-password-enroll-01",
        },
    )
    assert calls[2][1] == "/v1/accounts/acct_01/two-factor/enroll/begin"
    assert calls[3] == (
        "POST",
        "/v1/accounts/acct_01/two-factor/enroll/confirm",
        {
            "challenge_id": "challenge_a1_02",
            "code": totp_value,
            "idempotency_key": "idem-mfa-confirm-01",
        },
    )
    result_dump = json.dumps(
        {
            "password": password_result.to_dict(),
            "begin": begin_result.to_dict(),
            "confirm": confirm_result.to_dict(),
        }
    )
    assert password_value not in result_dump
    assert totp_value not in result_dump
    assert "confirmation_challenge_id" not in result_dump
    assert confirm_result.recovery_codes == (
        "RECOVERY-A1-1001",
        "RECOVERY-A1-1002",
    )


def test_legacy_security_mutations_fail_closed_before_transport() -> None:
    calls: list[object] = []
    client = UnifiedIdentityClient(
        "https://identity.example",
        transport=lambda *args: calls.append(args) or {},
    )

    with pytest.raises(UnifiedIdentityContractError, match="not routable"):
        client.mutate_password(
            "acct_01",
            "set",
            mutation_ticket_id="ticket_01",
            step_up_receipt_id="receipt_01",
            idempotency_key="idem-password-legacy",
        )
    with pytest.raises(UnifiedIdentityContractError, match="not routable"):
        client.mutate_two_factor(
            "acct_01",
            "disable",
            mutation_ticket_id="ticket_01",
            step_up_receipt_id="receipt_01",
            idempotency_key="idem-mfa-legacy",
        )
    assert calls == []


def test_client_helpers_emit_public_reference_only_requests_and_parse_dtos() -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def transport(method: str, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        path = urlparse(url).path
        calls.append((method, path, dict(payload)))
        if path.endswith("/credentials"):
            return {"credentials": [_credential("google"), _credential("wechat")]}
        if path.endswith("/memberships"):
            return {"memberships": [_membership()]}
        if path.endswith("/credentials/wechat/link"):
            return {
                "link_id": "link_wechat",
                "account_id": "acct_canonical",
                "provider": "wechat",
                "status": "pending",
                "expires_at": NOW,
                "authorize_url": "https://open.weixin.qq.com/connect/qrconnect",
                "verification_required": True,
            }
        if path.endswith("/credentials/cred_google/unlink"):
            return {
                "account_id": "acct_canonical",
                "credential_id": "cred_google",
                "provider": "google",
                "unlinked": True,
                "revocation_status": "revoked",
            }
        if path.endswith("/merge"):
            return {
                "merge_id": "merge_01",
                "canonical_account": _account(),
                "merged_account_ids": ["acct_source"],
                "credentials_repointed": 1,
                "memberships_repointed": 1,
                "completed_at": NOW,
            }
        if path.endswith("/recovery/start"):
            return {
                "recovery_id": "recovery_01",
                "account_id": "acct_canonical",
                "provider": "phone",
                "destination_hint": "+86 138****8000",
                "status": "pending",
                "expires_at": NOW,
                "attempts_remaining": 5,
            }
        if path.endswith("/recovery/recovery_01/complete"):
            return _account()
        if path.endswith("/accounts/acct_canonical"):
            return _account()
        raise AssertionError(path)

    client = UnifiedIdentityClient("http://localhost:8787/", transport=transport)
    assert client.get_account("acct_canonical").account_id == "acct_canonical"
    assert len(client.list_credentials("acct_canonical")) == 2
    assert client.list_memberships("acct_canonical")[0].role == "owner"
    assert client.link_credential(
        "acct_canonical", "wechat", idempotency_key="idem_link"
    ).provider == "wechat"
    assert client.unlink_credential(
        "acct_canonical",
        "cred_google",
        step_up_receipt_id="stepup_01",
        idempotency_key="idem_unlink",
    ).unlinked is True
    assert client.merge_accounts(
        "acct_canonical",
        "acct_source",
        step_up_receipt_id="stepup_02",
        idempotency_key="idem_merge",
    ).credentials_repointed == 1
    assert client.start_recovery(
        "acct_canonical", "phone", idempotency_key="idem_recovery"
    ).attempts_remaining == 5
    assert client.complete_recovery(
        "acct_canonical",
        "recovery_01",
        verification_receipt_id="verification_receipt_01",
        idempotency_key="idem_complete",
    ).status == "active"

    request_dump = json.dumps(calls)
    for forbidden in (
        "access_token",
        "authorization_code",
        "client_secret",
        "password",
        '"otp"',
        "refresh_token",
    ):
        assert forbidden not in request_dump
    assert ("POST", "/v1/accounts/acct_canonical/merge", {
        "source_account_id": "acct_source",
        "step_up_receipt_id": "stepup_02",
        "idempotency_key": "idem_merge",
    }) in calls


def test_client_rejects_raw_verification_material_before_transport() -> None:
    calls: list[object] = []
    client = UnifiedIdentityClient(
        "http://localhost:8787",
        transport=lambda *args: calls.append(args) or {},
    )

    with pytest.raises(TypeError):
        client.complete_recovery(  # type: ignore[call-arg]
            "acct_canonical",
            "recovery_01",
            otp="123456",
            idempotency_key="idem",
        )
    with pytest.raises(UnifiedIdentityContractError) as exc:
        client.merge_accounts(
            "acct_same",
            "acct_same",
            step_up_receipt_id="stepup",
            idempotency_key="idem",
        )
    assert exc.value.code == "identity_merge_cycle"
    assert calls == []


@pytest.mark.parametrize("provider", UNIFIED_IDENTITY_PROVIDERS)
def test_client_preserves_final_credential_unlink_protection_code(
    provider: str,
) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def transport(method: str, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append((method, urlparse(url).path, dict(payload)))
        return {
            "error": {
                "code": "identity_last_credential_unlink_forbidden",
                "message": "at least one active login credential must remain",
                "retryable": False,
                "provider": provider,
            }
        }

    client = UnifiedIdentityClient("http://localhost:8787", transport=transport)
    with pytest.raises(UnifiedIdentityContractError) as exc:
        client.unlink_credential(
            "acct_canonical",
            f"cred_{provider}",
            step_up_receipt_id="stepup_final_credential",
            idempotency_key=f"idem_unlink_{provider}",
        )

    assert exc.value.code == "identity_last_credential_unlink_forbidden"
    assert len(calls) == 1
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith(f"/credentials/cred_{provider}/unlink")
