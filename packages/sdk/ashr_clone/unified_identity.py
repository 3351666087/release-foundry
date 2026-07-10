from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote

from .api_client import redact_text

UNIFIED_IDENTITY_SCHEMA_VERSION = "ashr.clone.unified_identity.v1"
UNIFIED_IDENTITY_PROVIDERS = (
    "github",
    "google",
    "wechat",
    "qq",
    "alipay",
    "phone",
    "email",
)
UNIFIED_IDENTITY_ACCOUNT_STATUSES = ("active", "suspended", "merged", "recovery_locked")
UNIFIED_IDENTITY_CREDENTIAL_STATUSES = (
    "pending",
    "active",
    "revocation_pending",
    "revoked",
)
UNIFIED_IDENTITY_MEMBERSHIP_ROLES = ("owner", "admin", "developer", "viewer", "billing")
UNIFIED_IDENTITY_MEMBERSHIP_STATUSES = ("invited", "active", "suspended", "removed")
UNIFIED_IDENTITY_ERROR_CODES = (
    "identity_invalid_request",
    "identity_account_not_found",
    "identity_account_suspended",
    "identity_provider_not_supported",
    "identity_credential_not_found",
    "identity_credential_already_linked",
    "identity_credential_conflict",
    "identity_last_credential_unlink_forbidden",
    "identity_membership_not_found",
    "identity_membership_forbidden",
    "identity_link_expired",
    "identity_link_replayed",
    "identity_merge_conflict",
    "identity_merge_cycle",
    "identity_merge_requires_step_up",
    "identity_recovery_not_found",
    "identity_recovery_expired",
    "identity_recovery_replayed",
    "identity_recovery_rate_limited",
    "identity_recovery_locked",
    "identity_verification_required",
    "identity_verification_failed",
    "identity_store_failed",
)

_FORBIDDEN_PUBLIC_KEYS = {
    "access_token",
    "authorization",
    "authorization_code",
    "client_secret",
    "code_verifier",
    "cookie",
    "email",
    "id_token",
    "nonce",
    "otp",
    "password",
    "phone",
    "refresh_token",
    "secret",
    "session_token",
    "state",
    "provider_subject_sha256",
    "subject_digest",
    "identifier_sha256",
    "token",
    "token_ref",
    "token_ref_id",
    "revocation_outbox_id",
}
_FORBIDDEN_KEY_SUFFIXES = (
    "_access_token",
    "_authorization_code",
    "_client_secret",
    "_code_verifier",
    "_id_token",
    "_otp",
    "_password",
    "_refresh_token",
    "_secret",
    "_session_token",
)
_RECOVERY_PROVIDERS = ("phone", "email")
_FORBIDDEN_CANONICAL_KEYS = frozenset(
    "".join(character for character in key if character.isalnum())
    for key in _FORBIDDEN_PUBLIC_KEYS
)


class UnifiedIdentityContractError(ValueError):
    def __init__(self, message: str, *, code: str = "identity_invalid_request") -> None:
        if code not in UNIFIED_IDENTITY_ERROR_CODES:
            raise ValueError("unknown unified identity error code")
        self.code = code
        self.message = redact_text(message)
        super().__init__(self.message)


def normalize_identity_provider(provider: str) -> str:
    normalized = str(provider or "").strip().lower()
    if normalized not in UNIFIED_IDENTITY_PROVIDERS:
        raise UnifiedIdentityContractError(
            "identity provider is not supported",
            code="identity_provider_not_supported",
        )
    return normalized


def unified_identity_contract_manifest() -> dict[str, Any]:
    return {
        "schema_version": UNIFIED_IDENTITY_SCHEMA_VERSION,
        "subject_model": "one_account_many_credentials",
        "providers": list(UNIFIED_IDENTITY_PROVIDERS),
        "account_statuses": list(UNIFIED_IDENTITY_ACCOUNT_STATUSES),
        "credential_statuses": list(UNIFIED_IDENTITY_CREDENTIAL_STATUSES),
        "membership_roles": list(UNIFIED_IDENTITY_MEMBERSHIP_ROLES),
        "membership_statuses": list(UNIFIED_IDENTITY_MEMBERSHIP_STATUSES),
        "stable_error_codes": list(UNIFIED_IDENTITY_ERROR_CODES),
        "invariants": {
            "provider_identity_is_credential_not_account": True,
            "email_match_does_not_merge_accounts": True,
            "memberships_attach_to_canonical_account": True,
            "merge_preserves_memberships": True,
            "merge_repoints_credentials_atomically": True,
            "last_active_credential_cannot_be_unlinked": True,
            "recovery_requires_single_use_verification_receipt": True,
        },
        "public_safety": {
            "raw_email_present": False,
            "raw_phone_present": False,
            "raw_password_present": False,
            "raw_otp_present": False,
            "oauth_code_present": False,
            "oauth_token_present": False,
            "provider_secret_present": False,
            "provider_subject_digest_present": False,
            "provider_subject_presence_marker_only": True,
        },
    }


@dataclass(frozen=True)
class IdentityCredential:
    credential_id: str
    account_id: str
    provider: str
    provider_subject_present: bool
    status: str
    verified: bool
    display_hint: str
    linked_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "IdentityCredential":
        _assert_public_safe(payload)
        provider = normalize_identity_provider(str(payload.get("provider") or ""))
        status = _enum(
            "credential status",
            payload.get("status"),
            UNIFIED_IDENTITY_CREDENTIAL_STATUSES,
        )
        hint = _display_hint(provider, payload.get("display_hint"))
        return cls(
            credential_id=_identifier("credential_id", payload.get("credential_id")),
            account_id=_identifier("account_id", payload.get("account_id")),
            provider=provider,
            provider_subject_present=_boolean(
                "provider_subject_present", payload.get("provider_subject_present")
            ),
            status=status,
            verified=_boolean("verified", payload.get("verified")),
            display_hint=hint,
            linked_at=_timestamp("linked_at", payload.get("linked_at")),
            last_used_at=_optional_timestamp("last_used_at", payload.get("last_used_at")),
            revoked_at=_optional_timestamp("revoked_at", payload.get("revoked_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "credential_id": self.credential_id,
            "account_id": self.account_id,
            "provider": self.provider,
            "provider_subject_present": self.provider_subject_present,
            "status": self.status,
            "verified": self.verified,
            "display_hint": self.display_hint,
            "linked_at": self.linked_at,
            "last_used_at": self.last_used_at,
            "revoked_at": self.revoked_at,
        }


@dataclass(frozen=True)
class IdentityMembership:
    membership_id: str
    account_id: str
    tenant_id: str
    project_id: str | None
    role: str
    status: str
    joined_at: str

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "IdentityMembership":
        _assert_public_safe(payload)
        project_value = payload.get("project_id")
        return cls(
            membership_id=_identifier("membership_id", payload.get("membership_id")),
            account_id=_identifier("account_id", payload.get("account_id")),
            tenant_id=_identifier("tenant_id", payload.get("tenant_id")),
            project_id=_identifier("project_id", project_value) if project_value else None,
            role=_enum("membership role", payload.get("role"), UNIFIED_IDENTITY_MEMBERSHIP_ROLES),
            status=_enum(
                "membership status",
                payload.get("status"),
                UNIFIED_IDENTITY_MEMBERSHIP_STATUSES,
            ),
            joined_at=_timestamp("joined_at", payload.get("joined_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "membership_id": self.membership_id,
            "account_id": self.account_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "role": self.role,
            "status": self.status,
            "joined_at": self.joined_at,
        }


@dataclass(frozen=True)
class UnifiedAccount:
    account_id: str
    status: str
    display_name: str | None
    created_at: str
    updated_at: str
    merged_into_account_id: str | None = None
    credentials: tuple[IdentityCredential, ...] = ()
    memberships: tuple[IdentityMembership, ...] = ()

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "UnifiedAccount":
        _assert_public_safe(payload)
        account_id = _identifier("account_id", payload.get("account_id"))
        credentials = tuple(
            IdentityCredential.from_public_response(item)
            for item in _mapping_sequence("credentials", payload.get("credentials", ()))
        )
        memberships = tuple(
            IdentityMembership.from_public_response(item)
            for item in _mapping_sequence("memberships", payload.get("memberships", ()))
        )
        if any(item.account_id != account_id for item in (*credentials, *memberships)):
            raise UnifiedIdentityContractError("nested identity resource account mismatch")
        merged_value = payload.get("merged_into_account_id")
        return cls(
            account_id=account_id,
            status=_enum(
                "account status",
                payload.get("status"),
                UNIFIED_IDENTITY_ACCOUNT_STATUSES,
            ),
            display_name=_public_text(payload.get("display_name")),
            created_at=_timestamp("created_at", payload.get("created_at")),
            updated_at=_timestamp("updated_at", payload.get("updated_at")),
            merged_into_account_id=(
                _identifier("merged_into_account_id", merged_value) if merged_value else None
            ),
            credentials=credentials,
            memberships=memberships,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": UNIFIED_IDENTITY_SCHEMA_VERSION,
            "account_id": self.account_id,
            "status": self.status,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "merged_into_account_id": self.merged_into_account_id,
            "credentials": [item.to_dict() for item in self.credentials],
            "memberships": [item.to_dict() for item in self.memberships],
        }


@dataclass(frozen=True)
class IdentityLink:
    link_id: str
    account_id: str
    provider: str
    status: str
    expires_at: str
    authorize_url: str | None = None
    verification_required: bool = True

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "IdentityLink":
        _assert_public_safe(payload)
        authorize_url = payload.get("authorize_url")
        return cls(
            link_id=_identifier("link_id", payload.get("link_id")),
            account_id=_identifier("account_id", payload.get("account_id")),
            provider=normalize_identity_provider(str(payload.get("provider") or "")),
            status=_enum("link status", payload.get("status"), ("pending", "linked", "expired")),
            expires_at=_timestamp("expires_at", payload.get("expires_at")),
            authorize_url=_public_url("authorize_url", authorize_url) if authorize_url else None,
            verification_required=_boolean(
                "verification_required", payload.get("verification_required", True)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "account_id": self.account_id,
            "provider": self.provider,
            "status": self.status,
            "expires_at": self.expires_at,
            "authorize_url": self.authorize_url,
            "verification_required": self.verification_required,
        }


@dataclass(frozen=True)
class IdentityUnlink:
    account_id: str
    credential_id: str
    provider: str
    unlinked: bool
    revocation_status: str

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "IdentityUnlink":
        _assert_public_safe(payload)
        return cls(
            account_id=_identifier("account_id", payload.get("account_id")),
            credential_id=_identifier("credential_id", payload.get("credential_id")),
            provider=normalize_identity_provider(str(payload.get("provider") or "")),
            unlinked=_boolean("unlinked", payload.get("unlinked")),
            revocation_status=_enum(
                "revocation status",
                payload.get("revocation_status"),
                ("revoked", "not_required", "pending", "failed"),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "credential_id": self.credential_id,
            "provider": self.provider,
            "unlinked": self.unlinked,
            "revocation_status": self.revocation_status,
        }


@dataclass(frozen=True)
class IdentityMerge:
    merge_id: str
    canonical_account: UnifiedAccount
    merged_account_ids: tuple[str, ...]
    credentials_repointed: int
    memberships_repointed: int
    completed_at: str

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "IdentityMerge":
        _assert_public_safe(payload)
        account_payload = payload.get("canonical_account")
        if not isinstance(account_payload, Mapping):
            raise UnifiedIdentityContractError("canonical_account is required")
        canonical = UnifiedAccount.from_public_response(account_payload)
        merged_ids = tuple(
            _identifier("merged_account_id", item)
            for item in _scalar_sequence("merged_account_ids", payload.get("merged_account_ids"))
        )
        if canonical.account_id in merged_ids:
            raise UnifiedIdentityContractError(
                "canonical account cannot be listed as merged",
                code="identity_merge_cycle",
            )
        return cls(
            merge_id=_identifier("merge_id", payload.get("merge_id")),
            canonical_account=canonical,
            merged_account_ids=merged_ids,
            credentials_repointed=_non_negative_int(
                "credentials_repointed", payload.get("credentials_repointed")
            ),
            memberships_repointed=_non_negative_int(
                "memberships_repointed", payload.get("memberships_repointed")
            ),
            completed_at=_timestamp("completed_at", payload.get("completed_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "merge_id": self.merge_id,
            "canonical_account": self.canonical_account.to_dict(),
            "merged_account_ids": list(self.merged_account_ids),
            "credentials_repointed": self.credentials_repointed,
            "memberships_repointed": self.memberships_repointed,
            "completed_at": self.completed_at,
        }


@dataclass(frozen=True)
class IdentityRecovery:
    recovery_id: str
    account_id: str
    provider: str
    destination_hint: str
    status: str
    expires_at: str
    attempts_remaining: int

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "IdentityRecovery":
        _assert_public_safe(payload)
        provider = normalize_identity_provider(str(payload.get("provider") or ""))
        if provider not in _RECOVERY_PROVIDERS:
            raise UnifiedIdentityContractError(
                "recovery provider must be phone or email",
                code="identity_provider_not_supported",
            )
        return cls(
            recovery_id=_identifier("recovery_id", payload.get("recovery_id")),
            account_id=_identifier("account_id", payload.get("account_id")),
            provider=provider,
            destination_hint=_display_hint(provider, payload.get("destination_hint")),
            status=_enum(
                "recovery status",
                payload.get("status"),
                ("pending", "verified", "completed", "expired", "locked"),
            ),
            expires_at=_timestamp("expires_at", payload.get("expires_at")),
            attempts_remaining=_non_negative_int(
                "attempts_remaining", payload.get("attempts_remaining")
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "account_id": self.account_id,
            "provider": self.provider,
            "destination_hint": self.destination_hint,
            "status": self.status,
            "expires_at": self.expires_at,
            "attempts_remaining": self.attempts_remaining,
        }


@dataclass(frozen=True)
class UnifiedIdentityError:
    code: str
    message: str
    retryable: bool
    provider: str | None = None
    retry_after_seconds: int | None = None

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "UnifiedIdentityError":
        _assert_public_safe(payload)
        error = payload.get("error") if isinstance(payload.get("error"), Mapping) else payload
        code = str(error.get("code") or "")
        if code not in UNIFIED_IDENTITY_ERROR_CODES:
            raise UnifiedIdentityContractError("unknown unified identity error code")
        provider_value = error.get("provider")
        retry_after = error.get("retry_after_seconds")
        return cls(
            code=code,
            message=_public_text(error.get("message")) or "",
            retryable=_boolean("retryable", error.get("retryable", False)),
            provider=normalize_identity_provider(str(provider_value)) if provider_value else None,
            retry_after_seconds=(
                _non_negative_int("retry_after_seconds", retry_after)
                if retry_after is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "provider": self.provider,
            "retry_after_seconds": self.retry_after_seconds,
        }


IdentityTransport = Callable[[str, str, Mapping[str, Any]], Mapping[str, Any]]


class UnifiedIdentityClient:
    """Typed public-contract client; authentication and provider secrets stay transport-owned."""

    def __init__(self, base_url: str, *, transport: IdentityTransport) -> None:
        normalized = str(base_url or "").strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise UnifiedIdentityContractError("base_url must be HTTP or HTTPS")
        self.base_url = normalized
        self._transport = transport

    def get_account(self, account_id: str) -> UnifiedAccount:
        return UnifiedAccount.from_public_response(
            self._request("GET", identity_account_route(account_id), {})
        )

    def list_credentials(self, account_id: str) -> tuple[IdentityCredential, ...]:
        payload = self._request("GET", identity_credentials_route(account_id), {})
        return tuple(
            IdentityCredential.from_public_response(item)
            for item in _mapping_sequence("credentials", payload.get("credentials"))
        )

    def list_memberships(self, account_id: str) -> tuple[IdentityMembership, ...]:
        payload = self._request("GET", identity_memberships_route(account_id), {})
        return tuple(
            IdentityMembership.from_public_response(item)
            for item in _mapping_sequence("memberships", payload.get("memberships"))
        )

    def link_credential(
        self,
        account_id: str,
        provider: str,
        *,
        verification_receipt_id: str | None = None,
        idempotency_key: str,
    ) -> IdentityLink:
        normalized_provider = normalize_identity_provider(provider)
        payload: dict[str, Any] = {
            "provider": normalized_provider,
            "idempotency_key": _identifier("idempotency_key", idempotency_key),
        }
        if verification_receipt_id:
            payload["verification_receipt_id"] = _identifier(
                "verification_receipt_id", verification_receipt_id
            )
        return IdentityLink.from_public_response(
            self._request(
                "POST",
                identity_link_route(account_id, normalized_provider),
                payload,
            )
        )

    def unlink_credential(
        self,
        account_id: str,
        credential_id: str,
        *,
        step_up_receipt_id: str,
        idempotency_key: str,
    ) -> IdentityUnlink:
        return IdentityUnlink.from_public_response(
            self._request(
                "POST",
                identity_unlink_route(account_id, credential_id),
                {
                    "step_up_receipt_id": _identifier(
                        "step_up_receipt_id", step_up_receipt_id
                    ),
                    "idempotency_key": _identifier("idempotency_key", idempotency_key),
                },
            )
        )

    def merge_accounts(
        self,
        canonical_account_id: str,
        source_account_id: str,
        *,
        step_up_receipt_id: str,
        idempotency_key: str,
    ) -> IdentityMerge:
        canonical = _identifier("canonical_account_id", canonical_account_id)
        source = _identifier("source_account_id", source_account_id)
        if canonical == source:
            raise UnifiedIdentityContractError(
                "source and canonical accounts must differ",
                code="identity_merge_cycle",
            )
        return IdentityMerge.from_public_response(
            self._request(
                "POST",
                identity_merge_route(canonical),
                {
                    "source_account_id": source,
                    "step_up_receipt_id": _identifier(
                        "step_up_receipt_id", step_up_receipt_id
                    ),
                    "idempotency_key": _identifier("idempotency_key", idempotency_key),
                },
            )
        )

    def start_recovery(
        self,
        account_id: str,
        provider: str,
        *,
        idempotency_key: str,
    ) -> IdentityRecovery:
        normalized_provider = normalize_identity_provider(provider)
        if normalized_provider not in _RECOVERY_PROVIDERS:
            raise UnifiedIdentityContractError(
                "recovery provider must be phone or email",
                code="identity_provider_not_supported",
            )
        return IdentityRecovery.from_public_response(
            self._request(
                "POST",
                identity_recovery_start_route(account_id),
                {
                    "provider": normalized_provider,
                    "idempotency_key": _identifier("idempotency_key", idempotency_key),
                },
            )
        )

    def complete_recovery(
        self,
        account_id: str,
        recovery_id: str,
        *,
        verification_receipt_id: str,
        idempotency_key: str,
    ) -> UnifiedAccount:
        return UnifiedAccount.from_public_response(
            self._request(
                "POST",
                identity_recovery_complete_route(account_id, recovery_id),
                {
                    "verification_receipt_id": _identifier(
                        "verification_receipt_id", verification_receipt_id
                    ),
                    "idempotency_key": _identifier("idempotency_key", idempotency_key),
                },
            )
        )

    def _request(
        self, method: str, path: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        _assert_public_safe(payload)
        response = self._transport(method, f"{self.base_url}{path}", dict(payload))
        if not isinstance(response, Mapping):
            raise UnifiedIdentityContractError("identity transport must return an object")
        _assert_public_safe(response)
        result = response.get("result") if isinstance(response.get("result"), Mapping) else response
        error = response.get("error")
        if isinstance(error, Mapping):
            parsed = UnifiedIdentityError.from_public_response(error)
            raise UnifiedIdentityContractError(parsed.message or parsed.code, code=parsed.code)
        return result


def identity_account_route(account_id: str) -> str:
    return f"/v1/accounts/{_segment('account_id', account_id)}"


def identity_credentials_route(account_id: str) -> str:
    return f"{identity_account_route(account_id)}/credentials"


def identity_memberships_route(account_id: str) -> str:
    return f"{identity_account_route(account_id)}/memberships"


def identity_link_route(account_id: str, provider: str) -> str:
    return (
        f"{identity_credentials_route(account_id)}/"
        f"{quote(normalize_identity_provider(provider), safe='')}/link"
    )


def identity_unlink_route(account_id: str, credential_id: str) -> str:
    return (
        f"{identity_credentials_route(account_id)}/"
        f"{_segment('credential_id', credential_id)}/unlink"
    )


def identity_merge_route(canonical_account_id: str) -> str:
    return f"{identity_account_route(canonical_account_id)}/merge"


def identity_recovery_start_route(account_id: str) -> str:
    return f"{identity_account_route(account_id)}/recovery/start"


def identity_recovery_complete_route(account_id: str, recovery_id: str) -> str:
    return (
        f"{identity_account_route(account_id)}/recovery/"
        f"{_segment('recovery_id', recovery_id)}/complete"
    )


def _assert_public_safe(payload: Mapping[str, Any]) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).strip().lower().replace("-", "_")
                canonical = "".join(
                    character for character in normalized if character.isalnum()
                )
                if normalized in _FORBIDDEN_PUBLIC_KEYS or normalized.endswith(
                    _FORBIDDEN_KEY_SUFFIXES
                ) or canonical in _FORBIDDEN_CANONICAL_KEYS:
                    raise UnifiedIdentityContractError(
                        f"public identity payload must not include {normalized}"
                    )
                visit(item)
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for item in value:
                visit(item)

    visit(payload)


def _identifier(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 255 or any(char.isspace() for char in normalized):
        raise UnifiedIdentityContractError(f"{name} must be a non-empty opaque identifier")
    return normalized


def _segment(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 255:
        raise UnifiedIdentityContractError(f"{name} must be a non-empty route identifier")
    return quote(normalized, safe="")


def _enum(name: str, value: Any, allowed: Sequence[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise UnifiedIdentityContractError(f"{name} is invalid")
    return normalized


def _boolean(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise UnifiedIdentityContractError(f"{name} must be a boolean")
    return value


def _timestamp(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise UnifiedIdentityContractError(f"{name} must be an ISO-8601 timestamp") from exc
    return normalized


def _optional_timestamp(name: str, value: Any) -> str | None:
    return _timestamp(name, value) if value else None


def _display_hint(provider: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 120:
        raise UnifiedIdentityContractError("display hint is required")
    if provider == "email" and ("@" not in normalized or "*" not in normalized):
        raise UnifiedIdentityContractError("email display hint must be masked")
    if provider == "phone":
        digits = "".join(char for char in normalized if char.isdigit())
        # A public hint may retain country code, a short carrier prefix, and
        # the final four digits, but must never contain a full E.164 number.
        if "*" not in normalized or len(digits) > 9:
            raise UnifiedIdentityContractError("phone display hint must be masked")
    safe = redact_text(normalized)
    if safe == "[redacted]":
        raise UnifiedIdentityContractError("display hint contains raw identity data")
    return safe


def _public_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    return redact_text(normalized)


def _public_url(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized.startswith(("http://", "https://")):
        raise UnifiedIdentityContractError(f"{name} must be HTTP or HTTPS")
    return normalized


def _mapping_sequence(name: str, value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise UnifiedIdentityContractError(f"{name} must be an array")
    if any(not isinstance(item, Mapping) for item in value):
        raise UnifiedIdentityContractError(f"{name} entries must be objects")
    return tuple(value)


def _scalar_sequence(name: str, value: Any) -> tuple[Any, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise UnifiedIdentityContractError(f"{name} must be an array")
    return tuple(value)


def _non_negative_int(name: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise UnifiedIdentityContractError(f"{name} must be a non-negative integer")
    return value
