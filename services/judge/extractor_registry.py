"""Versioned, issuer-attested qualification records for artifact extractors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping


EXTRACTOR_QUALIFICATION_SCHEMA_VERSION = "a2.extractor_qualification.v1"
EXTRACTOR_QUALIFICATION_PROJECTION_VERSION = "a2.extractor_qualification_public.v1"
PROMOTION_STATUSES = frozenset({"candidate", "qualified", "suspended", "revoked"})
QUALIFIABLE_STATUSES = frozenset({"qualified"})
REQUIRED_QUALITY_THRESHOLDS = frozenset(
    {"minimum_precision", "minimum_recall", "minimum_content_coverage"}
)
REQUIRED_SECURITY_CHECKS = frozenset(
    {"malformed_input", "resource_limits", "path_isolation", "active_content_disabled"}
)
REQUIRED_OFFLINE_CHECKS = frozenset(
    {"network_disabled", "model_artifacts_pinned", "dependency_lock_verified"}
)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}$")
_DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
_LICENSE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-.+ ]{0,127}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+$")
_LANGUAGE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_ALLOWED_FIELDS = frozenset(
    {
        "schema_version",
        "record_id",
        "extractor",
        "runtime",
        "artifact_digest",
        "license",
        "supported_media_types",
        "supported_languages",
        "quality_thresholds",
        "security_checks",
        "offline_checks",
        "promotion_status",
        "valid_from",
        "valid_until",
        "issuer",
        "issuer_attestation",
        "record_hash",
    }
)
_EXTRACTOR_FIELDS = frozenset({"id", "version"})
_RUNTIME_FIELDS = frozenset({"id", "version", "platform"})
_ISSUER_FIELDS = frozenset({"id", "authority"})
_ATTESTATION_FIELDS = frozenset({"method", "reference", "issued_at"})


class ExtractorQualificationError(ValueError):
    """Fail-closed qualification failure containing public-safe blockers."""

    def __init__(self, blockers: list[str], projection: dict[str, Any]):
        self.blockers = sorted(set(blockers))
        self.projection = projection
        super().__init__(", ".join(self.blockers))


@dataclass(frozen=True)
class QualifiedExtractor:
    extractor_id: str
    extractor_version: str
    runtime_id: str
    runtime_version: str
    runtime_platform: str
    artifact_digest: str
    supported_media_types: tuple[str, ...]
    supported_languages: tuple[str, ...]
    record_id: str
    record_hash: str
    issuer_id: str
    valid_until: str


class ExtractorQualificationRegistry:
    """In-memory record registry with external revocation state.

    Record hashes provide deterministic integrity only. Issuer attestations are
    independent trust assertions and must be accepted only from configured
    authorities; this class does not claim cryptographic signature security.
    """

    def __init__(
        self,
        records: list[Mapping[str, Any]] | None = None,
        *,
        trusted_issuers: Mapping[str, set[str] | frozenset[str]] | None = None,
    ) -> None:
        self._trusted_issuers = {
            str(issuer_id): frozenset(str(authority) for authority in authorities)
            for issuer_id, authorities in (trusted_issuers or {}).items()
        }
        self._records: dict[tuple[str, str], dict[str, Any]] = {}
        self._revocations: dict[str, str] = {}
        for record in records or []:
            self.register(record)

    def register(self, record: Mapping[str, Any]) -> None:
        blockers = validate_qualification_record(
            record,
            trusted_issuers=self._trusted_issuers,
        )
        if blockers:
            raise ExtractorQualificationError(
                blockers,
                public_qualification_projection(record, blockers=blockers),
            )
        normalized = _json_copy(record)
        key = (normalized["extractor"]["id"], normalized["extractor"]["version"])
        existing = self._records.get(key)
        if existing and existing["record_hash"] != normalized["record_hash"]:
            blockers = ["extractor_version_record_conflict"]
            raise ExtractorQualificationError(
                blockers,
                public_qualification_projection(record, blockers=blockers),
            )
        self._records[key] = normalized

    def revoke(self, record_id: str, *, reason_code: str) -> None:
        if not _valid_id(record_id) or not _valid_id(reason_code):
            raise ValueError("record_id and reason_code must be public-safe identifiers")
        if not any(record["record_id"] == record_id for record in self._records.values()):
            raise KeyError("qualification record is not registered")
        self._revocations[record_id] = reason_code

    def qualify(
        self,
        deployment: Mapping[str, Any],
        *,
        media_type: str,
        language: str,
        observed_quality: Mapping[str, Any],
        now: str,
    ) -> QualifiedExtractor:
        blockers = _validate_deployment(deployment)
        if not isinstance(deployment, Mapping):
            raise ExtractorQualificationError(
                blockers,
                _missing_projection("", "", blockers),
            )
        extractor_id = str(deployment.get("extractor_id") or "")
        extractor_version = str(deployment.get("extractor_version") or "")
        record = self._records.get((extractor_id, extractor_version))
        if record is None:
            blockers.append("qualification_record_not_found")
            projection = _missing_projection(extractor_id, extractor_version, blockers)
            raise ExtractorQualificationError(blockers, projection)

        blockers.extend(
            validate_qualification_record(
                record,
                trusted_issuers=self._trusted_issuers,
                now=now,
            )
        )
        if record["record_id"] in self._revocations:
            blockers.append("qualification_revoked")
        if record["promotion_status"] not in QUALIFIABLE_STATUSES:
            blockers.append("promotion_status_not_qualified")

        runtime = record["runtime"]
        for deployment_field, expected in (
            ("runtime_id", runtime["id"]),
            ("runtime_version", runtime["version"]),
            ("runtime_platform", runtime["platform"]),
            ("artifact_digest", record["artifact_digest"]),
        ):
            if deployment.get(deployment_field) != expected:
                blockers.append(f"{deployment_field}_mismatch")

        if media_type not in record["supported_media_types"]:
            blockers.append("media_type_not_supported")
        if language not in record["supported_languages"]:
            blockers.append("language_not_supported")
        blockers.extend(_quality_blockers(observed_quality, record["quality_thresholds"]))

        if blockers:
            raise ExtractorQualificationError(
                blockers,
                public_qualification_projection(
                    record,
                    blockers=blockers,
                    revoked=record["record_id"] in self._revocations,
                ),
            )
        return QualifiedExtractor(
            extractor_id=record["extractor"]["id"],
            extractor_version=record["extractor"]["version"],
            runtime_id=runtime["id"],
            runtime_version=runtime["version"],
            runtime_platform=runtime["platform"],
            artifact_digest=record["artifact_digest"],
            supported_media_types=tuple(record["supported_media_types"]),
            supported_languages=tuple(record["supported_languages"]),
            record_id=record["record_id"],
            record_hash=record["record_hash"],
            issuer_id=record["issuer"]["id"],
            valid_until=record["valid_until"],
        )

    def public_records(self, *, now: str | None = None) -> dict[str, Any]:
        records = []
        for record in sorted(self._records.values(), key=lambda item: item["record_id"]):
            blockers = validate_qualification_record(
                record,
                trusted_issuers=self._trusted_issuers,
                now=now,
            )
            revoked = record["record_id"] in self._revocations
            if revoked:
                blockers.append("qualification_revoked")
            records.append(
                public_qualification_projection(record, blockers=blockers, revoked=revoked)
            )
        return {
            "schema_version": EXTRACTOR_QUALIFICATION_PROJECTION_VERSION,
            "records": records,
            "record_count": len(records),
            "raw_attestations_included": False,
            "secret_material_included": False,
        }


def qualification_record_hash(record: Mapping[str, Any]) -> str:
    """Return a deterministic integrity hash; this is not a signature."""
    payload = {key: value for key, value in record.items() if key != "record_hash"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_qualification_record(
    record: Mapping[str, Any],
    *,
    trusted_issuers: Mapping[str, frozenset[str] | set[str]] | None = None,
    now: str | None = None,
) -> list[str]:
    blockers: list[str] = []
    if not isinstance(record, Mapping):
        return ["qualification_record_invalid"]
    unknown = set(record) - _ALLOWED_FIELDS
    missing = _ALLOWED_FIELDS - set(record)
    if unknown:
        blockers.append("qualification_unknown_fields")
    if missing:
        blockers.append("qualification_required_fields_missing")
    if record.get("schema_version") != EXTRACTOR_QUALIFICATION_SCHEMA_VERSION:
        blockers.append("qualification_schema_unsupported")
    if not _valid_id(record.get("record_id")):
        blockers.append("record_id_invalid")

    extractor = record.get("extractor")
    if not _exact_mapping(extractor, _EXTRACTOR_FIELDS):
        blockers.append("extractor_identity_invalid")
    else:
        if not _valid_id(extractor.get("id")):
            blockers.append("extractor_id_invalid")
        if not _valid_version(extractor.get("version")):
            blockers.append("extractor_version_invalid")

    runtime = record.get("runtime")
    if not _exact_mapping(runtime, _RUNTIME_FIELDS):
        blockers.append("runtime_invalid")
    elif any(not _valid_id(runtime.get(field)) for field in _RUNTIME_FIELDS):
        blockers.append("runtime_invalid")
    if not isinstance(record.get("artifact_digest"), str) or not _DIGEST.fullmatch(
        record["artifact_digest"]
    ):
        blockers.append("artifact_digest_invalid")
    if not isinstance(record.get("license"), str) or not _LICENSE.fullmatch(record["license"]):
        blockers.append("license_invalid")

    blockers.extend(
        _string_list_blockers(
            record.get("supported_media_types"), "supported_media_types"
        )
    )
    if isinstance(record.get("supported_media_types"), list) and any(
        not isinstance(value, str) or not _MEDIA_TYPE.fullmatch(value)
        for value in record["supported_media_types"]
    ):
        blockers.append("supported_media_types_invalid")
    blockers.extend(
        _string_list_blockers(
            record.get("supported_languages"), "supported_languages"
        )
    )
    if isinstance(record.get("supported_languages"), list) and any(
        not isinstance(value, str) or not _LANGUAGE.fullmatch(value)
        for value in record["supported_languages"]
    ):
        blockers.append("supported_languages_invalid")

    thresholds = record.get("quality_thresholds")
    if not isinstance(thresholds, Mapping):
        blockers.append("quality_thresholds_invalid")
    else:
        if set(thresholds) != REQUIRED_QUALITY_THRESHOLDS:
            blockers.append("quality_thresholds_incomplete")
        if any(not _unit_interval(value) for value in thresholds.values()):
            blockers.append("quality_thresholds_invalid")
    blockers.extend(
        _check_matrix_blockers(record.get("security_checks"), REQUIRED_SECURITY_CHECKS, "security")
    )
    blockers.extend(
        _check_matrix_blockers(record.get("offline_checks"), REQUIRED_OFFLINE_CHECKS, "offline")
    )

    status = record.get("promotion_status")
    if status not in PROMOTION_STATUSES:
        blockers.append("promotion_status_invalid")
    valid_from = _parse_time(record.get("valid_from"), "valid_from", blockers)
    valid_until = _parse_time(record.get("valid_until"), "valid_until", blockers)
    current = _parse_time(now, "qualification_time", blockers) if now is not None else None
    if valid_from and valid_until and valid_until <= valid_from:
        blockers.append("qualification_validity_invalid")
    if current and valid_from and current < valid_from:
        blockers.append("qualification_not_yet_valid")
    if current and valid_until and current >= valid_until:
        blockers.append("qualification_expired")

    issuer = record.get("issuer")
    if not _exact_mapping(issuer, _ISSUER_FIELDS):
        blockers.append("issuer_invalid")
    else:
        issuer_id = issuer.get("id")
        authority = issuer.get("authority")
        if not _valid_id(issuer_id) or not _valid_id(authority):
            blockers.append("issuer_invalid")
        if isinstance(extractor, Mapping) and issuer_id == extractor.get("id"):
            blockers.append("extractor_self_attestation_forbidden")
        if trusted_issuers is not None and authority not in trusted_issuers.get(
            str(issuer_id), frozenset()
        ):
            blockers.append("issuer_not_trusted")

    attestation = record.get("issuer_attestation")
    if not _exact_mapping(attestation, _ATTESTATION_FIELDS):
        blockers.append("issuer_attestation_invalid")
    else:
        if attestation.get("method") != "external-record":
            blockers.append("issuer_attestation_method_unsupported")
        if not _valid_id(attestation.get("reference")):
            blockers.append("issuer_attestation_reference_invalid")
        _parse_time(attestation.get("issued_at"), "attestation_issued_at", blockers)

    supplied_hash = record.get("record_hash")
    if not isinstance(supplied_hash, str) or not _DIGEST.fullmatch(supplied_hash):
        blockers.append("record_hash_invalid")
    else:
        try:
            expected_hash = qualification_record_hash(record)
        except (TypeError, ValueError):
            blockers.append("record_hash_payload_invalid")
        else:
            if supplied_hash != expected_hash:
                blockers.append("record_hash_mismatch")
    return sorted(set(blockers))


def public_qualification_projection(
    record: Mapping[str, Any],
    *,
    blockers: list[str] | None = None,
    revoked: bool = False,
) -> dict[str, Any]:
    extractor = record.get("extractor") if isinstance(record.get("extractor"), Mapping) else {}
    runtime = record.get("runtime") if isinstance(record.get("runtime"), Mapping) else {}
    issuer = record.get("issuer") if isinstance(record.get("issuer"), Mapping) else {}
    attestation = (
        record.get("issuer_attestation")
        if isinstance(record.get("issuer_attestation"), Mapping)
        else {}
    )
    status = "revoked" if revoked else str(record.get("promotion_status") or "invalid")
    safe = {
        "schema_version": EXTRACTOR_QUALIFICATION_PROJECTION_VERSION,
        "record_id": _safe_identifier(record.get("record_id")),
        "extractor": {
            "id": _safe_identifier(extractor.get("id")),
            "version": _safe_version(extractor.get("version")),
        },
        "runtime": {
            "id": _safe_identifier(runtime.get("id")),
            "version": _safe_identifier(runtime.get("version")),
            "platform": _safe_identifier(runtime.get("platform")),
        },
        "artifact_digest": _safe_digest(record.get("artifact_digest")),
        "license": _safe_license(record.get("license")),
        "supported_media_types": _safe_string_list(record.get("supported_media_types")),
        "supported_languages": _safe_string_list(record.get("supported_languages")),
        "promotion_status": status,
        "valid_from": str(record.get("valid_from") or ""),
        "valid_until": str(record.get("valid_until") or ""),
        "issuer": {
            "id": _safe_identifier(issuer.get("id")),
            "authority": _safe_identifier(issuer.get("authority")),
        },
        "attestation_method": str(attestation.get("method") or ""),
        "attestation_reference_hash": _hash_text(str(attestation.get("reference") or "")),
        "record_hash": str(record.get("record_hash") or ""),
        "integrity_mechanism": "sha256-canonical-json",
        "cryptographic_signature_verified": False,
        "status": "eligible" if not blockers and status == "qualified" else "blocked",
        "blockers": sorted(set(blockers or [])),
        "raw_attestation_included": False,
        "secret_material_included": False,
    }
    return safe


def _validate_deployment(deployment: Mapping[str, Any]) -> list[str]:
    required = {
        "extractor_id",
        "extractor_version",
        "runtime_id",
        "runtime_version",
        "runtime_platform",
        "artifact_digest",
    }
    if not isinstance(deployment, Mapping) or set(deployment) != required:
        return ["extractor_deployment_invalid"]
    blockers = []
    for field in required - {"artifact_digest"}:
        if not _valid_id(deployment.get(field)):
            blockers.append(f"{field}_invalid")
    if not isinstance(deployment.get("artifact_digest"), str) or not _DIGEST.fullmatch(
        deployment["artifact_digest"]
    ):
        blockers.append("artifact_digest_invalid")
    return blockers


def _quality_blockers(
    observed: Mapping[str, Any], thresholds: Mapping[str, Any]
) -> list[str]:
    if not isinstance(observed, Mapping) or set(observed) != REQUIRED_QUALITY_THRESHOLDS:
        return ["observed_quality_incomplete"]
    blockers = []
    for metric in sorted(REQUIRED_QUALITY_THRESHOLDS):
        value = observed.get(metric)
        if not _unit_interval(value):
            blockers.append(f"observed_{metric}_invalid")
        elif value < thresholds[metric]:
            blockers.append(f"{metric}_below_threshold")
    return blockers


def _check_matrix_blockers(value: Any, required: frozenset[str], prefix: str) -> list[str]:
    if not isinstance(value, Mapping):
        return [f"{prefix}_checks_invalid"]
    blockers = []
    if set(value) != required:
        blockers.append(f"{prefix}_checks_incomplete")
    if any(result is not True for result in value.values()):
        blockers.append(f"{prefix}_checks_failed")
    return blockers


def _string_list_blockers(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{field}_invalid"]
    if len(value) != len(set(value)) or value != sorted(value):
        return [f"{field}_not_canonical"]
    return []


def _parse_time(value: Any, field: str, blockers: list[str]) -> datetime | None:
    if not isinstance(value, str):
        blockers.append(f"{field}_invalid")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        blockers.append(f"{field}_invalid")
        return None
    if parsed.tzinfo is None:
        blockers.append(f"{field}_timezone_required")
        return None
    return parsed.astimezone(timezone.utc)


def _exact_mapping(value: Any, fields: frozenset[str]) -> bool:
    return isinstance(value, Mapping) and set(value) == fields


def _valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _valid_version(value: Any) -> bool:
    return isinstance(value, str) and bool(_VERSION.fullmatch(value))


def _unit_interval(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, str)
        and (_MEDIA_TYPE.fullmatch(item) or _LANGUAGE.fullmatch(item))
    ]


def _safe_identifier(value: Any) -> str:
    return value if _valid_id(value) else ""


def _safe_version(value: Any) -> str:
    return value if _valid_version(value) else ""


def _safe_digest(value: Any) -> str:
    return value if isinstance(value, str) and _DIGEST.fullmatch(value) else ""


def _safe_license(value: Any) -> str:
    return value if isinstance(value, str) and _LICENSE.fullmatch(value) else ""


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, allow_nan=False))


def _missing_projection(
    extractor_id: str, extractor_version: str, blockers: list[str]
) -> dict[str, Any]:
    return {
        "schema_version": EXTRACTOR_QUALIFICATION_PROJECTION_VERSION,
        "record_id": "",
        "extractor": {"id": extractor_id, "version": extractor_version},
        "promotion_status": "unregistered",
        "status": "blocked",
        "blockers": sorted(set(blockers)),
        "raw_attestation_included": False,
        "secret_material_included": False,
    }
