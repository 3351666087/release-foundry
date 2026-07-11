from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from threading import RLock
from typing import Any, Callable, Mapping, Protocol, Sequence, TypeVar
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
IDENTITY_VERIFICATION_PROVIDERS = ("email", "phone")
IDENTITY_VERIFICATION_PURPOSES = ("binding", "login", "recovery")
IDENTITY_VERIFICATION_CHALLENGE_STATUSES = (
    "pending",
    "verified",
    "consumed",
    "expired",
    "locked",
)
IDENTITY_VERIFICATION_RECEIPT_STATUSES = ("verified", "consumed", "expired")
IDENTITY_VERIFICATION_AUDIT_EVENT_TYPES = (
    "challenge_issued",
    "challenge_rejected",
    "challenge_locked",
    "challenge_expired",
    "challenge_consumed",
)
IDENTITY_VERIFICATION_AUDIT_OUTCOME_CODES = (
    "issued",
    "cooldown_active",
    "context_mismatch",
    "proof_mismatch",
    "attempts_exhausted",
    "expired",
    "consumed",
)
IDENTITY_VERIFICATION_PUBLIC_SURFACE = (
    "IdentityVerificationAbuseDimensions",
    "IdentityVerificationAdminFilter",
    "IdentityVerificationAuditEvent",
    "IdentityVerificationAuditEventPage",
    "IdentityVerificationDigestEnvelope",
    "IdentityVerificationDurableReceipt",
    "IdentityVerificationDurableReceiptPage",
    "IdentityVerificationDurableStore",
    "IdentityVerificationMemoryStore",
    "IdentityVerificationTransactionCoordinator",
)
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
    "identity_verification_expired",
    "identity_verification_locked",
    "identity_verification_replayed",
    "identity_verification_rate_limited",
    "identity_verification_resend_too_soon",
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
    "email_address",
    "id_token",
    "nonce",
    "otp",
    "password",
    "phone",
    "phone_number",
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
    "destination",
    "destination_value",
    "verification_code",
    "verification_value",
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
            "verification_challenges_are_provider_neutral": True,
            "verification_receipts_are_single_use": True,
            "verification_login_does_not_merge_by_destination": True,
        },
        "verification": {
            "providers": list(IDENTITY_VERIFICATION_PROVIDERS),
            "purposes": list(IDENTITY_VERIFICATION_PURPOSES),
            "challenge_statuses": list(IDENTITY_VERIFICATION_CHALLENGE_STATUSES),
            "receipt_statuses": list(IDENTITY_VERIFICATION_RECEIPT_STATUSES),
            "destination_input": "opaque_reference_only",
            "code_input": "opaque_reference_only",
            "ttl_required": True,
            "attempt_cap_required": True,
            "resend_cooldown_required": True,
            "single_use_required": True,
            "durable_receipt_records": True,
            "append_only_audit": True,
            "admin_queries_route_neutral": True,
            "digest_only_envelopes": True,
            "atomic_receipt_consumption": True,
            "anti_enumerating_public_failures": True,
            "media_safe_metadata": True,
            "public_surface": list(IDENTITY_VERIFICATION_PUBLIC_SURFACE),
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
class IdentityVerificationChallenge:
    challenge_id: str
    provider: str
    purpose: str
    status: str
    destination_hint: str
    destination_digest_ref: str
    created_at: str
    expires_at: str
    ttl_seconds: int
    attempt_cap: int
    attempts_remaining: int
    resend_cooldown_seconds: int
    resend_available_at: str
    single_use: bool
    account_id: str | None = None
    verified_at: str | None = None
    consumed_at: str | None = None

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityVerificationChallenge":
        _assert_public_safe(payload)
        provider = normalize_verification_provider(payload.get("provider"))
        purpose = normalize_verification_purpose(payload.get("purpose"))
        status = _enum(
            "verification challenge status",
            payload.get("status"),
            IDENTITY_VERIFICATION_CHALLENGE_STATUSES,
        )
        ttl_seconds = _positive_int("ttl_seconds", payload.get("ttl_seconds"))
        attempt_cap = _positive_int("attempt_cap", payload.get("attempt_cap"))
        attempts_remaining = _non_negative_int(
            "attempts_remaining", payload.get("attempts_remaining")
        )
        if attempts_remaining > attempt_cap:
            raise UnifiedIdentityContractError(
                "attempts_remaining cannot exceed attempt_cap"
            )
        single_use = _boolean("single_use", payload.get("single_use"))
        if not single_use:
            raise UnifiedIdentityContractError(
                "verification challenge must be single-use"
            )
        account_value = payload.get("account_id")
        verified_at = _optional_timestamp("verified_at", payload.get("verified_at"))
        consumed_at = _optional_timestamp("consumed_at", payload.get("consumed_at"))
        if status == "verified" and verified_at is None:
            raise UnifiedIdentityContractError(
                "verified challenge requires verified_at"
            )
        if status == "consumed" and consumed_at is None:
            raise UnifiedIdentityContractError(
                "consumed challenge requires consumed_at"
            )
        return cls(
            challenge_id=_identifier("challenge_id", payload.get("challenge_id")),
            provider=provider,
            purpose=purpose,
            status=status,
            destination_hint=_display_hint(provider, payload.get("destination_hint")),
            destination_digest_ref=_digest_reference(
                "destination_digest_ref", payload.get("destination_digest_ref")
            ),
            created_at=_timestamp("created_at", payload.get("created_at")),
            expires_at=_timestamp("expires_at", payload.get("expires_at")),
            ttl_seconds=ttl_seconds,
            attempt_cap=attempt_cap,
            attempts_remaining=attempts_remaining,
            resend_cooldown_seconds=_positive_int(
                "resend_cooldown_seconds", payload.get("resend_cooldown_seconds")
            ),
            resend_available_at=_timestamp(
                "resend_available_at", payload.get("resend_available_at")
            ),
            single_use=single_use,
            account_id=(
                _identifier("account_id", account_value) if account_value else None
            ),
            verified_at=verified_at,
            consumed_at=consumed_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "provider": self.provider,
            "purpose": self.purpose,
            "status": self.status,
            "destination_hint": self.destination_hint,
            "destination_digest_ref": self.destination_digest_ref,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "ttl_seconds": self.ttl_seconds,
            "attempt_cap": self.attempt_cap,
            "attempts_remaining": self.attempts_remaining,
            "resend_cooldown_seconds": self.resend_cooldown_seconds,
            "resend_available_at": self.resend_available_at,
            "single_use": self.single_use,
            "account_id": self.account_id,
            "verified_at": self.verified_at,
            "consumed_at": self.consumed_at,
        }


@dataclass(frozen=True)
class IdentityVerificationReceipt:
    receipt_id: str
    challenge_id: str
    provider: str
    purpose: str
    status: str
    destination_digest_ref: str
    verified_at: str
    expires_at: str
    single_use: bool
    account_id: str | None = None
    consumed_at: str | None = None

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityVerificationReceipt":
        _assert_public_safe(payload)
        status = _enum(
            "verification receipt status",
            payload.get("status"),
            IDENTITY_VERIFICATION_RECEIPT_STATUSES,
        )
        single_use = _boolean("single_use", payload.get("single_use"))
        if not single_use:
            raise UnifiedIdentityContractError(
                "verification receipt must be single-use"
            )
        consumed_at = _optional_timestamp("consumed_at", payload.get("consumed_at"))
        if status == "consumed" and consumed_at is None:
            raise UnifiedIdentityContractError(
                "consumed receipt requires consumed_at"
            )
        account_value = payload.get("account_id")
        return cls(
            receipt_id=_identifier("receipt_id", payload.get("receipt_id")),
            challenge_id=_identifier("challenge_id", payload.get("challenge_id")),
            provider=normalize_verification_provider(payload.get("provider")),
            purpose=normalize_verification_purpose(payload.get("purpose")),
            status=status,
            destination_digest_ref=_digest_reference(
                "destination_digest_ref", payload.get("destination_digest_ref")
            ),
            verified_at=_timestamp("verified_at", payload.get("verified_at")),
            expires_at=_timestamp("expires_at", payload.get("expires_at")),
            single_use=single_use,
            account_id=(
                _identifier("account_id", account_value) if account_value else None
            ),
            consumed_at=consumed_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "challenge_id": self.challenge_id,
            "provider": self.provider,
            "purpose": self.purpose,
            "status": self.status,
            "destination_digest_ref": self.destination_digest_ref,
            "verified_at": self.verified_at,
            "expires_at": self.expires_at,
            "single_use": self.single_use,
            "account_id": self.account_id,
            "consumed_at": self.consumed_at,
        }


@dataclass(frozen=True)
class IdentityVerificationDurableReceipt:
    receipt: IdentityVerificationReceipt
    tenant_id: str
    project_id: str
    principal_id: str | None
    created_at: str
    audit_event_id: str

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityVerificationDurableReceipt":
        _assert_public_safe(payload)
        receipt = payload.get("receipt")
        if not isinstance(receipt, Mapping):
            raise UnifiedIdentityContractError("receipt must be an object")
        return cls(
            receipt=IdentityVerificationReceipt.from_public_response(receipt),
            tenant_id=_identifier("tenant_id", payload.get("tenant_id")),
            project_id=_identifier("project_id", payload.get("project_id")),
            principal_id=_optional_identifier(
                "principal_id", payload.get("principal_id")
            ),
            created_at=_timestamp("created_at", payload.get("created_at")),
            audit_event_id=_identifier(
                "audit_event_id", payload.get("audit_event_id")
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt": self.receipt.to_dict(),
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "principal_id": self.principal_id,
            "created_at": self.created_at,
            "audit_event_id": self.audit_event_id,
        }


@dataclass(frozen=True)
class IdentityVerificationAuditEvent:
    event_id: str
    event_type: str
    outcome_code: str
    tenant_id: str
    project_id: str
    provider: str
    purpose: str
    attempt_number: int
    created_at: str
    challenge_id: str | None
    receipt_id: str | None
    principal_id: str | None
    account_id: str | None
    metadata: Mapping[str, Any]

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityVerificationAuditEvent":
        _assert_public_safe(payload)
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise UnifiedIdentityContractError("metadata must be an object")
        return cls(
            event_id=_identifier("event_id", payload.get("event_id")),
            event_type=_enum(
                "verification audit event type",
                payload.get("event_type"),
                IDENTITY_VERIFICATION_AUDIT_EVENT_TYPES,
            ),
            outcome_code=_enum(
                "verification audit outcome code",
                payload.get("outcome_code"),
                IDENTITY_VERIFICATION_AUDIT_OUTCOME_CODES,
            ),
            tenant_id=_identifier("tenant_id", payload.get("tenant_id")),
            project_id=_identifier("project_id", payload.get("project_id")),
            provider=normalize_verification_provider(payload.get("provider")),
            purpose=normalize_verification_purpose(payload.get("purpose")),
            attempt_number=_non_negative_int(
                "attempt_number", payload.get("attempt_number")
            ),
            created_at=_timestamp("created_at", payload.get("created_at")),
            challenge_id=_optional_identifier(
                "challenge_id", payload.get("challenge_id")
            ),
            receipt_id=_optional_identifier("receipt_id", payload.get("receipt_id")),
            principal_id=_optional_identifier(
                "principal_id", payload.get("principal_id")
            ),
            account_id=_optional_identifier("account_id", payload.get("account_id")),
            metadata=dict(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "outcome_code": self.outcome_code,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "provider": self.provider,
            "purpose": self.purpose,
            "attempt_number": self.attempt_number,
            "created_at": self.created_at,
            "challenge_id": self.challenge_id,
            "receipt_id": self.receipt_id,
            "principal_id": self.principal_id,
            "account_id": self.account_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class IdentityVerificationAdminFilter:
    tenant_id: str
    project_id: str
    provider: str | None = None
    purpose: str | None = None
    challenge_id: str | None = None
    receipt_id: str | None = None
    principal_id: str | None = None
    account_id: str | None = None
    event_type: str | None = None
    outcome_code: str | None = None
    created_after: str | None = None
    created_before: str | None = None
    cursor: str | None = None
    limit: int = 50

    def to_public_query(self) -> dict[str, Any]:
        query: dict[str, Any] = {
            "tenant_id": _identifier("tenant_id", self.tenant_id),
            "project_id": _identifier("project_id", self.project_id),
            "limit": _bounded_positive_int("limit", self.limit, 1, 200),
        }
        for name, value in {
            "challenge_id": self.challenge_id,
            "receipt_id": self.receipt_id,
            "principal_id": self.principal_id,
            "account_id": self.account_id,
            "cursor": self.cursor,
        }.items():
            normalized = _optional_identifier(name, value)
            if normalized is not None:
                query[name] = normalized
        if self.provider is not None:
            query["provider"] = normalize_verification_provider(self.provider)
        if self.purpose is not None:
            query["purpose"] = normalize_verification_purpose(self.purpose)
        if self.event_type is not None:
            query["event_type"] = _enum(
                "verification audit event type",
                self.event_type,
                IDENTITY_VERIFICATION_AUDIT_EVENT_TYPES,
            )
        if self.outcome_code is not None:
            query["outcome_code"] = _enum(
                "verification audit outcome code",
                self.outcome_code,
                IDENTITY_VERIFICATION_AUDIT_OUTCOME_CODES,
            )
        created_after = _optional_timestamp("created_after", self.created_after)
        created_before = _optional_timestamp("created_before", self.created_before)
        if created_after is not None:
            query["created_after"] = created_after
        if created_before is not None:
            query["created_before"] = created_before
        if (
            created_after is not None
            and created_before is not None
            and _parse_timestamp(created_after) > _parse_timestamp(created_before)
        ):
            raise UnifiedIdentityContractError(
                "created_after cannot be later than created_before"
            )
        _assert_public_safe(query)
        return query


@dataclass(frozen=True)
class IdentityVerificationDurableReceiptPage:
    items: tuple[IdentityVerificationDurableReceipt, ...]
    next_cursor: str | None

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityVerificationDurableReceiptPage":
        _assert_public_safe(payload)
        return cls(
            items=tuple(
                IdentityVerificationDurableReceipt.from_public_response(item)
                for item in _mapping_sequence("items", payload.get("items"))
            ),
            next_cursor=_optional_identifier(
                "next_cursor", payload.get("next_cursor")
            ),
        )


@dataclass(frozen=True)
class IdentityVerificationAuditEventPage:
    items: tuple[IdentityVerificationAuditEvent, ...]
    next_cursor: str | None

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityVerificationAuditEventPage":
        _assert_public_safe(payload)
        return cls(
            items=tuple(
                IdentityVerificationAuditEvent.from_public_response(item)
                for item in _mapping_sequence("items", payload.get("items"))
            ),
            next_cursor=_optional_identifier(
                "next_cursor", payload.get("next_cursor")
            ),
        )


@dataclass(frozen=True)
class IdentityVerificationDigestEnvelope:
    tenant_id: str
    project_id: str
    provider: str
    purpose: str
    challenge_id: str
    destination_digest_ref: str
    request_context_digest_ref: str
    idempotency_digest_ref: str
    request_digest_ref: str
    receipt_id: str | None = None
    principal_id: str | None = None
    account_id: str | None = None

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityVerificationDigestEnvelope":
        _assert_public_safe(payload)
        return cls(
            tenant_id=_identifier("tenant_id", payload.get("tenant_id")),
            project_id=_identifier("project_id", payload.get("project_id")),
            provider=normalize_verification_provider(payload.get("provider")),
            purpose=normalize_verification_purpose(payload.get("purpose")),
            challenge_id=_identifier("challenge_id", payload.get("challenge_id")),
            destination_digest_ref=_digest_reference(
                "destination_digest_ref", payload.get("destination_digest_ref")
            ),
            request_context_digest_ref=_digest_reference(
                "request_context_digest_ref",
                payload.get("request_context_digest_ref"),
            ),
            idempotency_digest_ref=_digest_reference(
                "idempotency_digest_ref", payload.get("idempotency_digest_ref")
            ),
            request_digest_ref=_digest_reference(
                "request_digest_ref", payload.get("request_digest_ref")
            ),
            receipt_id=_optional_identifier("receipt_id", payload.get("receipt_id")),
            principal_id=_optional_identifier(
                "principal_id", payload.get("principal_id")
            ),
            account_id=_optional_identifier("account_id", payload.get("account_id")),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class IdentityVerificationAbuseDimensions:
    tenant_id: str
    project_id: str
    provider: str
    purpose: str
    destination_digest_ref: str
    request_context_digest_ref: str
    attempt_cap: int
    cooldown_seconds: int
    consecutive_failures: int = 0
    blocked_until: str | None = None
    principal_id: str | None = None
    account_id: str | None = None

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityVerificationAbuseDimensions":
        _assert_public_safe(payload)
        return cls(
            tenant_id=_identifier("tenant_id", payload.get("tenant_id")),
            project_id=_identifier("project_id", payload.get("project_id")),
            provider=normalize_verification_provider(payload.get("provider")),
            purpose=normalize_verification_purpose(payload.get("purpose")),
            destination_digest_ref=_digest_reference(
                "destination_digest_ref", payload.get("destination_digest_ref")
            ),
            request_context_digest_ref=_digest_reference(
                "request_context_digest_ref",
                payload.get("request_context_digest_ref"),
            ),
            attempt_cap=_bounded_positive_int(
                "attempt_cap", payload.get("attempt_cap"), 1, 100
            ),
            cooldown_seconds=_bounded_non_negative_int(
                "cooldown_seconds", payload.get("cooldown_seconds"), 86_400
            ),
            consecutive_failures=_bounded_non_negative_int(
                "consecutive_failures",
                payload.get("consecutive_failures", 0),
                1_000_000,
            ),
            blocked_until=_optional_timestamp(
                "blocked_until", payload.get("blocked_until")
            ),
            principal_id=_optional_identifier(
                "principal_id", payload.get("principal_id")
            ),
            account_id=_optional_identifier("account_id", payload.get("account_id")),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class IdentityVerificationDurableStore(Protocol):
    def persist_receipt(self, receipt: IdentityVerificationDurableReceipt) -> None: ...

    def get_receipt(
        self, tenant_id: str, project_id: str, receipt_id: str
    ) -> IdentityVerificationDurableReceipt | None: ...

    def list_receipts(
        self, query: IdentityVerificationAdminFilter
    ) -> IdentityVerificationDurableReceiptPage: ...

    def append_audit_event(self, event: IdentityVerificationAuditEvent) -> None: ...

    def list_audit_events(
        self, query: IdentityVerificationAdminFilter
    ) -> IdentityVerificationAuditEventPage: ...

    def replace_receipt(
        self,
        expected: IdentityVerificationDurableReceipt,
        replacement: IdentityVerificationDurableReceipt,
        event: IdentityVerificationAuditEvent,
    ) -> None: ...


class IdentityVerificationMemoryStore:
    """Thread-safe public-contract store used for local SDK tests and replay."""

    def __init__(self) -> None:
        self._receipts: dict[
            tuple[str, str, str], IdentityVerificationDurableReceipt
        ] = {}
        self._events: dict[
            tuple[str, str, str], IdentityVerificationAuditEvent
        ] = {}
        self._lock = RLock()

    def persist_receipt(self, receipt: IdentityVerificationDurableReceipt) -> None:
        normalized = _clone_durable_receipt(receipt)
        key = self._receipt_key(normalized)
        with self._lock:
            if key in self._receipts:
                raise UnifiedIdentityContractError(
                    "verification receipt already exists",
                    code="identity_verification_replayed",
                )
            self._receipts[key] = normalized

    def get_receipt(
        self, tenant_id: str, project_id: str, receipt_id: str
    ) -> IdentityVerificationDurableReceipt | None:
        key = (
            _identifier("tenant_id", tenant_id),
            _identifier("project_id", project_id),
            _identifier("receipt_id", receipt_id),
        )
        with self._lock:
            value = self._receipts.get(key)
            return _clone_durable_receipt(value) if value is not None else None

    def list_receipts(
        self, query: IdentityVerificationAdminFilter
    ) -> IdentityVerificationDurableReceiptPage:
        filters = query.to_public_query()
        with self._lock:
            values = [
                value
                for value in self._receipts.values()
                if _matches_receipt(value, filters)
            ]
        values.sort(key=lambda value: (value.created_at, value.receipt.receipt_id))
        page, cursor = _paginate(values, filters)
        return IdentityVerificationDurableReceiptPage(
            tuple(_clone_durable_receipt(item) for item in page), cursor
        )

    def append_audit_event(self, event: IdentityVerificationAuditEvent) -> None:
        normalized = _clone_audit_event(event)
        key = (normalized.tenant_id, normalized.project_id, normalized.event_id)
        with self._lock:
            if key in self._events:
                raise UnifiedIdentityContractError("verification audit event already exists")
            self._events[key] = normalized

    def list_audit_events(
        self, query: IdentityVerificationAdminFilter
    ) -> IdentityVerificationAuditEventPage:
        filters = query.to_public_query()
        with self._lock:
            values = [
                value
                for value in self._events.values()
                if _matches_event(value, filters)
            ]
        values.sort(key=lambda value: (value.created_at, value.event_id))
        page, cursor = _paginate(values, filters)
        return IdentityVerificationAuditEventPage(
            tuple(_clone_audit_event(item) for item in page), cursor
        )

    def replace_receipt(
        self,
        expected: IdentityVerificationDurableReceipt,
        replacement: IdentityVerificationDurableReceipt,
        event: IdentityVerificationAuditEvent,
    ) -> None:
        current_key = self._receipt_key(expected)
        replacement_value = _clone_durable_receipt(replacement)
        event_value = _clone_audit_event(event)
        if self._receipt_key(replacement_value) != current_key:
            raise UnifiedIdentityContractError("receipt scope cannot change")
        event_key = (event_value.tenant_id, event_value.project_id, event_value.event_id)
        if event_key[:2] != current_key[:2]:
            raise UnifiedIdentityContractError("audit event scope mismatch")
        with self._lock:
            if self._receipts.get(current_key) != expected:
                raise UnifiedIdentityContractError(
                    "verification receipt is unavailable",
                    code="identity_verification_replayed",
                )
            if event_key in self._events:
                raise UnifiedIdentityContractError("verification audit event already exists")
            self._receipts[current_key] = replacement_value
            self._events[event_key] = event_value

    @staticmethod
    def _receipt_key(
        value: IdentityVerificationDurableReceipt,
    ) -> tuple[str, str, str]:
        return (value.tenant_id, value.project_id, value.receipt.receipt_id)


MutationResult = TypeVar("MutationResult")


class IdentityVerificationTransactionCoordinator:
    def __init__(self, store: IdentityVerificationDurableStore) -> None:
        self._store = store
        self._lock = RLock()

    def consume_receipt(
        self,
        tenant_id: str,
        project_id: str,
        receipt_id: str,
        event: IdentityVerificationAuditEvent,
        mutation: Callable[[IdentityVerificationReceipt], MutationResult],
        *,
        consumed_at: str,
    ) -> MutationResult:
        with self._lock:
            current = self._store.get_receipt(tenant_id, project_id, receipt_id)
            if current is None or current.receipt.status != "verified":
                raise UnifiedIdentityContractError(
                    "verification receipt is unavailable",
                    code="identity_verification_replayed",
                )
            timestamp = _timestamp("consumed_at", consumed_at)
            if _parse_timestamp(timestamp) >= _parse_timestamp(current.receipt.expires_at):
                raise UnifiedIdentityContractError(
                    "verification receipt is unavailable",
                    code="identity_verification_expired",
                )
            if (
                event.tenant_id != current.tenant_id
                or event.project_id != current.project_id
                or event.receipt_id != current.receipt.receipt_id
                or event.event_type != "challenge_consumed"
                or event.outcome_code != "consumed"
            ):
                raise UnifiedIdentityContractError("receipt consumption event mismatch")
            result = mutation(_clone_receipt(current.receipt))
            consumed = IdentityVerificationReceipt(
                **{
                    **current.receipt.__dict__,
                    "status": "consumed",
                    "consumed_at": timestamp,
                }
            )
            replacement = IdentityVerificationDurableReceipt(
                **{**current.__dict__, "receipt": consumed}
            )
            self._store.replace_receipt(current, replacement, event)
            return result


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

    def start_verification(
        self,
        provider: str,
        purpose: str,
        *,
        destination_ref: str,
        idempotency_key: str,
        account_id: str | None = None,
    ) -> IdentityVerificationChallenge:
        normalized_provider = normalize_verification_provider(provider)
        normalized_purpose = normalize_verification_purpose(purpose)
        payload: dict[str, Any] = {
            "provider": normalized_provider,
            "purpose": normalized_purpose,
            "destination_ref": _private_input_reference(
                "destination_ref", destination_ref
            ),
            "idempotency_key": _identifier("idempotency_key", idempotency_key),
        }
        if account_id is not None:
            payload["account_id"] = _identifier("account_id", account_id)
        if normalized_purpose in {"binding", "recovery"} and "account_id" not in payload:
            raise UnifiedIdentityContractError(
                f"{normalized_purpose} verification requires account_id"
            )
        return IdentityVerificationChallenge.from_public_response(
            self._request("POST", identity_verification_challenges_route(), payload)
        )

    def get_verification(
        self, challenge_id: str
    ) -> IdentityVerificationChallenge:
        return IdentityVerificationChallenge.from_public_response(
            self._request(
                "GET", identity_verification_challenge_route(challenge_id), {}
            )
        )

    def resend_verification(
        self,
        challenge_id: str,
        *,
        idempotency_key: str,
    ) -> IdentityVerificationChallenge:
        return IdentityVerificationChallenge.from_public_response(
            self._request(
                "POST",
                identity_verification_resend_route(challenge_id),
                {"idempotency_key": _identifier("idempotency_key", idempotency_key)},
            )
        )

    def verify_challenge(
        self,
        challenge_id: str,
        *,
        verification_code_ref: str,
        idempotency_key: str,
    ) -> IdentityVerificationReceipt:
        return IdentityVerificationReceipt.from_public_response(
            self._request(
                "POST",
                identity_verification_verify_route(challenge_id),
                {
                    "verification_code_ref": _private_input_reference(
                        "verification_code_ref", verification_code_ref
                    ),
                    "idempotency_key": _identifier("idempotency_key", idempotency_key),
                },
            )
        )

    def decode_durable_receipt_page(
        self, payload: Mapping[str, Any]
    ) -> IdentityVerificationDurableReceiptPage:
        return IdentityVerificationDurableReceiptPage.from_public_response(payload)

    def decode_verification_audit_page(
        self, payload: Mapping[str, Any]
    ) -> IdentityVerificationAuditEventPage:
        return IdentityVerificationAuditEventPage.from_public_response(payload)

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


def identity_verification_challenges_route() -> str:
    return "/v1/identity/verifications/challenges"


def identity_verification_challenge_route(challenge_id: str) -> str:
    return (
        f"{identity_verification_challenges_route()}/"
        f"{_segment('challenge_id', challenge_id)}"
    )


def identity_verification_resend_route(challenge_id: str) -> str:
    return f"{identity_verification_challenge_route(challenge_id)}/resend"


def identity_verification_verify_route(challenge_id: str) -> str:
    return f"{identity_verification_challenge_route(challenge_id)}/verify"


def normalize_verification_provider(provider: Any) -> str:
    normalized = normalize_identity_provider(str(provider or ""))
    if normalized not in IDENTITY_VERIFICATION_PROVIDERS:
        raise UnifiedIdentityContractError(
            "verification provider must be phone or email",
            code="identity_provider_not_supported",
        )
    return normalized


def normalize_verification_purpose(purpose: Any) -> str:
    return _enum(
        "verification purpose", purpose, IDENTITY_VERIFICATION_PURPOSES
    )


def _assert_public_safe(payload: Mapping[str, Any]) -> None:
    def visit(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).strip().lower().replace("-", "_")
                canonical = "".join(
                    character for character in normalized if character.isalnum()
                )
                safe_error_destination = (
                    normalized == "destination"
                    and path == ("error", "details")
                    and _is_safe_error_destination(item)
                )
                stable_error_code = normalized == "code" and path == ("error",)
                if not (safe_error_destination or stable_error_code) and (
                    normalized in _FORBIDDEN_PUBLIC_KEYS
                    or normalized.endswith(_FORBIDDEN_KEY_SUFFIXES)
                    or canonical in _FORBIDDEN_CANONICAL_KEYS
                ):
                    raise UnifiedIdentityContractError(
                        f"public identity payload must not include {normalized}"
                    )
                visit(item, (*path, normalized))
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for item in value:
                visit(item, path)

    visit(payload)


def _is_safe_error_destination(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 160:
        return False
    return not re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\+?[1-9]\d{7,14}",
        value,
    )


def _identifier(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 255 or any(char.isspace() for char in normalized):
        raise UnifiedIdentityContractError(f"{name} must be a non-empty opaque identifier")
    return normalized


def _optional_identifier(name: str, value: Any) -> str | None:
    return None if value is None or value == "" else _identifier(name, value)


def _private_input_reference(name: str, value: Any) -> str:
    normalized = _identifier(name, value)
    if ":" not in normalized:
        raise UnifiedIdentityContractError(
            f"{name} must be a namespaced opaque reference"
        )
    lowered = normalized.lower()
    if "@" in normalized or lowered.startswith(("mailto:", "tel:", "sms:")):
        raise UnifiedIdentityContractError(
            f"{name} must not contain raw destination or verification material"
        )
    return normalized


def _digest_reference(name: str, value: Any) -> str:
    normalized = _identifier(name, value)
    lowered = normalized.lower()
    if ":" not in normalized or lowered.startswith(
        ("sha256:", "sha-256:", "mailto:", "tel:")
    ):
        raise UnifiedIdentityContractError(
            f"{name} must be an opaque server-side digest reference"
        )
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
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise UnifiedIdentityContractError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise UnifiedIdentityContractError(f"{name} must include a timezone")
    return normalized


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


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


def _positive_int(name: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise UnifiedIdentityContractError(f"{name} must be a positive integer")
    return value


def _bounded_positive_int(
    name: str, value: Any, minimum: int, maximum: int
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > maximum
    ):
        raise UnifiedIdentityContractError(
            f"{name} must be an integer from {minimum} through {maximum}"
        )
    return value


def _bounded_non_negative_int(name: str, value: Any, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        or value > maximum
    ):
        raise UnifiedIdentityContractError(
            f"{name} must be a non-negative integer no greater than {maximum}"
        )
    return value


def _clone_receipt(value: IdentityVerificationReceipt) -> IdentityVerificationReceipt:
    return IdentityVerificationReceipt.from_public_response(value.to_dict())


def _clone_durable_receipt(
    value: IdentityVerificationDurableReceipt,
) -> IdentityVerificationDurableReceipt:
    return IdentityVerificationDurableReceipt.from_public_response(value.to_dict())


def _clone_audit_event(
    value: IdentityVerificationAuditEvent,
) -> IdentityVerificationAuditEvent:
    return IdentityVerificationAuditEvent.from_public_response(
        deepcopy(value.to_dict())
    )


def _matches_time(created_at: str, filters: Mapping[str, Any]) -> bool:
    value = _parse_timestamp(created_at)
    after = filters.get("created_after")
    before = filters.get("created_before")
    return not (
        (after is not None and value < _parse_timestamp(after))
        or (before is not None and value > _parse_timestamp(before))
    )


def _matches_receipt(
    value: IdentityVerificationDurableReceipt, filters: Mapping[str, Any]
) -> bool:
    receipt = value.receipt
    fields = {
        "tenant_id": value.tenant_id,
        "project_id": value.project_id,
        "provider": receipt.provider,
        "purpose": receipt.purpose,
        "challenge_id": receipt.challenge_id,
        "receipt_id": receipt.receipt_id,
        "principal_id": value.principal_id,
        "account_id": receipt.account_id,
    }
    return all(
        filters.get(name) is None or filters[name] == actual
        for name, actual in fields.items()
    ) and _matches_time(value.created_at, filters)


def _matches_event(
    value: IdentityVerificationAuditEvent, filters: Mapping[str, Any]
) -> bool:
    fields = {
        "tenant_id": value.tenant_id,
        "project_id": value.project_id,
        "provider": value.provider,
        "purpose": value.purpose,
        "challenge_id": value.challenge_id,
        "receipt_id": value.receipt_id,
        "principal_id": value.principal_id,
        "account_id": value.account_id,
        "event_type": value.event_type,
        "outcome_code": value.outcome_code,
    }
    return all(
        filters.get(name) is None or filters[name] == actual
        for name, actual in fields.items()
    ) and _matches_time(value.created_at, filters)


def _paginate(
    values: Sequence[Any], filters: Mapping[str, Any]
) -> tuple[Sequence[Any], str | None]:
    cursor = filters.get("cursor")
    if cursor:
        parts = cursor.split(":", 1)
        if (
            len(parts) != 2
            or parts[0] != "cursor"
            or not parts[1].isdigit()
        ):
            raise UnifiedIdentityContractError("cursor is invalid")
        start = int(parts[1])
    else:
        start = 0
    limit = filters["limit"]
    page = values[start : start + limit]
    next_offset = start + len(page)
    next_cursor = f"cursor:{next_offset}" if next_offset < len(values) else None
    return page, next_cursor
