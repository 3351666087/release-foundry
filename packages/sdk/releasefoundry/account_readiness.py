from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


ACCOUNT_READINESS_RECEIPT_VERSION = "a1-human-operator-receipt-v1"

PROVIDERS = frozenset(
    {
        "github_oauth",
        "google_oauth",
        "wechat_open_login",
        "alipay_login",
        "wechat_pay",
        "alipay_merchant",
        "domestic_bank_card",
    }
)
ENVIRONMENTS = frozenset({"sandbox", "production"})
STATUSES = frozenset(
    {
        "not_started",
        "applied",
        "under_review",
        "approved",
        "configured",
        "blocked",
        "rejected",
        "revoked",
    }
)

_FORBIDDEN_KEY_PARTS = (
    "secret",
    "password",
    "passwd",
    "token",
    "private_key",
    "api_key",
    "authorization_code",
    "otp",
    "cvv",
    "cvc",
    "pin",
    "pan",
    "card_number",
    "track_data",
    "cryptogram",
    "id_card",
    "identity_card",
    "passport",
    "business_license",
    "kyc_document",
    "kyc_file",
)
_FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:client_secret|access_token|refresh_token|api_key)\s*[:=]", re.IGNORECASE),
    re.compile(r"\b(?:cvv|cvc|otp|pin)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(
        r"(?:\u8eab\u4efd\u8bc1|\u62a4\u7167|\u8425\u4e1a\u6267\u7167|KYC)"
        r"\s*(?:\u626b\u63cf|\u7167\u7247|\u6587\u4ef6|\u53f7\u7801|\u53f7)",
        re.IGNORECASE,
    ),
)
_SAFE_ID_SUFFIX = re.compile(r"^[A-Za-z0-9_-]{4,16}$")
_SHA256_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_TIMESTAMP_FIELDS = ("observed_at", "submitted_at", "reviewed_at", "updated_at")


class AccountReadinessError(ValueError):
    """Raised when a Human Operator receipt is unsafe or malformed."""


@dataclass(frozen=True)
class AccountReadinessReceipt:
    provider: str
    environment: str
    status: str
    redirect_uris: tuple[str, ...]
    application_id_suffix: str | None
    application_fingerprint: str | None
    observed_at: str
    submitted_at: str | None = None
    reviewed_at: str | None = None
    updated_at: str | None = None
    receipt_id: str | None = None
    operator_note: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AccountReadinessReceipt":
        safe_payload = validate_account_readiness_receipt(payload)
        return cls(
            provider=safe_payload["provider"],
            environment=safe_payload["environment"],
            status=safe_payload["status"],
            redirect_uris=tuple(safe_payload["redirect_uris"]),
            application_id_suffix=safe_payload.get("application_id_suffix"),
            application_fingerprint=safe_payload.get("application_fingerprint"),
            observed_at=safe_payload["observed_at"],
            submitted_at=safe_payload.get("submitted_at"),
            reviewed_at=safe_payload.get("reviewed_at"),
            updated_at=safe_payload.get("updated_at"),
            receipt_id=safe_payload.get("receipt_id"),
            operator_note=safe_payload.get("operator_note"),
        )

    def to_public_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": ACCOUNT_READINESS_RECEIPT_VERSION,
            "provider": self.provider,
            "environment": self.environment,
            "status": self.status,
            "redirect_uris": list(self.redirect_uris),
            "application_id_suffix": self.application_id_suffix,
            "application_fingerprint": self.application_fingerprint,
            "observed_at": self.observed_at,
            "submitted_at": self.submitted_at,
            "reviewed_at": self.reviewed_at,
            "updated_at": self.updated_at,
            "receipt_id": self.receipt_id,
            "operator_note": self.operator_note,
            "contains_secrets": False,
            "contains_payment_card_data": False,
            "contains_kyc_material": False,
        }
        return {key: value for key, value in result.items() if value is not None}


def validate_account_readiness_receipt(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise AccountReadinessError("receipt must be a JSON object")
    _reject_sensitive_material(payload)

    allowed = {
        "schema_version",
        "provider",
        "environment",
        "status",
        "redirect_uris",
        "application_id_suffix",
        "application_fingerprint",
        "observed_at",
        "submitted_at",
        "reviewed_at",
        "updated_at",
        "receipt_id",
        "operator_note",
        "contains_secrets",
        "contains_payment_card_data",
        "contains_kyc_material",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise AccountReadinessError(f"unsupported receipt fields: {', '.join(unknown)}")
    if payload.get("schema_version", ACCOUNT_READINESS_RECEIPT_VERSION) != ACCOUNT_READINESS_RECEIPT_VERSION:
        raise AccountReadinessError("unsupported receipt schema_version")
    for field in ("contains_secrets", "contains_payment_card_data", "contains_kyc_material"):
        if payload.get(field, False) is not False:
            raise AccountReadinessError(f"{field} must be false")

    provider = _required_string(payload, "provider")
    environment = _required_string(payload, "environment")
    status = _required_string(payload, "status")
    if provider not in PROVIDERS:
        raise AccountReadinessError("unsupported provider")
    if environment not in ENVIRONMENTS:
        raise AccountReadinessError("environment must be sandbox or production")
    if status not in STATUSES:
        raise AccountReadinessError("unsupported status")

    suffix = _optional_string(payload, "application_id_suffix")
    fingerprint = _optional_string(payload, "application_fingerprint")
    if not suffix and not fingerprint:
        raise AccountReadinessError("application_id_suffix or application_fingerprint is required")
    if suffix and not _SAFE_ID_SUFFIX.fullmatch(suffix):
        raise AccountReadinessError("application_id_suffix must contain 4-16 safe suffix characters")
    if fingerprint and not _SHA256_FINGERPRINT.fullmatch(fingerprint):
        raise AccountReadinessError("application_fingerprint must use sha256:<64 lowercase hex>")

    redirect_uris = payload.get("redirect_uris")
    if not isinstance(redirect_uris, list):
        raise AccountReadinessError("redirect_uris must be a JSON array")
    if len(redirect_uris) > 10:
        raise AccountReadinessError("redirect_uris exceeds the maximum of 10")
    normalized_uris = [_validate_redirect_uri(uri, environment) for uri in redirect_uris]
    if provider in {"github_oauth", "google_oauth", "wechat_open_login", "alipay_login"} and not normalized_uris:
        raise AccountReadinessError("login providers require at least one redirect URI")

    timestamps: dict[str, str | None] = {}
    for field in _TIMESTAMP_FIELDS:
        value = _required_string(payload, field) if field == "observed_at" else _optional_string(payload, field)
        timestamps[field] = _validate_timestamp(value, field) if value else None

    receipt_id = _optional_string(payload, "receipt_id")
    if receipt_id and not re.fullmatch(r"[A-Za-z0-9._:-]{6,128}", receipt_id):
        raise AccountReadinessError("receipt_id contains unsupported characters")
    operator_note = _optional_string(payload, "operator_note")
    if operator_note and len(operator_note) > 500:
        raise AccountReadinessError("operator_note exceeds 500 characters")

    result: dict[str, Any] = {
        "schema_version": ACCOUNT_READINESS_RECEIPT_VERSION,
        "provider": provider,
        "environment": environment,
        "status": status,
        "redirect_uris": normalized_uris,
        "observed_at": timestamps["observed_at"],
        "contains_secrets": False,
        "contains_payment_card_data": False,
        "contains_kyc_material": False,
    }
    for key, value in (
        ("application_id_suffix", suffix),
        ("application_fingerprint", fingerprint),
        ("submitted_at", timestamps["submitted_at"]),
        ("reviewed_at", timestamps["reviewed_at"]),
        ("updated_at", timestamps["updated_at"]),
        ("receipt_id", receipt_id),
        ("operator_note", operator_note),
    ):
        if value is not None:
            result[key] = value
    return result


def build_receipt_template(provider: str, environment: str = "sandbox") -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise AccountReadinessError("unsupported provider")
    if environment not in ENVIRONMENTS:
        raise AccountReadinessError("environment must be sandbox or production")
    callback_providers = {"github_oauth", "google_oauth", "wechat_open_login", "alipay_login"}
    return {
        "schema_version": ACCOUNT_READINESS_RECEIPT_VERSION,
        "provider": provider,
        "application_id_suffix": "last4",
        "application_fingerprint": "sha256:" + hashlib.sha256(f"{provider}:replace-with-local-id".encode()).hexdigest(),
        "environment": environment,
        "redirect_uris": ["https://app.example.com/oauth/callback"] if provider in callback_providers else [],
        "status": "not_started",
        "observed_at": "2026-01-01T00:00:00+08:00",
        "receipt_id": f"operator:{provider}:replace",
        "operator_note": "Non-sensitive status only. Do not include secrets, payment-card data, or KYC materials.",
    }


def _reject_sensitive_material(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            public_safety_declaration = normalized in {
                "contains_secrets",
                "contains_payment_card_data",
                "contains_kyc_material",
            }
            if not public_safety_declaration and any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
                raise AccountReadinessError(f"sensitive field is forbidden at {path}")
            _reject_sensitive_material(nested, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_sensitive_material(nested, f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return
    if any(pattern.search(value) for pattern in _FORBIDDEN_VALUE_PATTERNS):
        raise AccountReadinessError(f"sensitive value is forbidden at {path}")
    for candidate in re.findall(r"(?:\d[ -]?){13,19}", value):
        digits = re.sub(r"\D", "", candidate)
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            raise AccountReadinessError(f"payment-card number is forbidden at {path}")


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        number = int(char)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def _validate_redirect_uri(value: Any, environment: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AccountReadinessError("redirect URI must be a non-empty string")
    uri = value.strip()
    parsed = urlparse(uri)
    if parsed.username or parsed.password or parsed.fragment:
        raise AccountReadinessError("redirect URI must not include userinfo or fragments")
    localhost = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (environment == "sandbox" and localhost and parsed.scheme == "http"):
        raise AccountReadinessError("redirect URI must use HTTPS; sandbox localhost may use HTTP")
    if not parsed.hostname:
        raise AccountReadinessError("redirect URI must include a host")
    return uri


def _validate_timestamp(value: str, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AccountReadinessError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise AccountReadinessError(f"{field} must include a timezone")
    return value


def _required_string(payload: Mapping[str, Any], field: str) -> str:
    value = _optional_string(payload, field)
    if value is None:
        raise AccountReadinessError(f"{field} is required")
    return value


def _optional_string(payload: Mapping[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AccountReadinessError(f"{field} must be a non-empty string")
    return value.strip()


def _load_json_object(path: str) -> Mapping[str, Any]:
    resolved = Path(path).expanduser().resolve()
    lowered_parts = {part.lower() for part in resolved.parts}
    if ".secrets" in lowered_parts or "private_refs" in lowered_parts:
        raise AccountReadinessError("refusing to read receipt from a secret/private evidence directory")
    payload = json.loads(resolved.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, Mapping):
        raise AccountReadinessError("receipt file must contain a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate public-safe Human Operator account-readiness receipts.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    template = subparsers.add_parser("template", help="Print a non-sensitive receipt template.")
    template.add_argument("--provider", choices=sorted(PROVIDERS), required=True)
    template.add_argument("--environment", choices=sorted(ENVIRONMENTS), default="sandbox")
    validate = subparsers.add_parser("validate", help="Validate and normalize a receipt JSON file.")
    validate.add_argument("--file", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "template":
            output = build_receipt_template(args.provider, args.environment)
        else:
            output = AccountReadinessReceipt.from_mapping(_load_json_object(args.file)).to_public_dict()
        print(json.dumps(output, indent=2, sort_keys=True, ensure_ascii=True))
        return 0
    except (AccountReadinessError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
