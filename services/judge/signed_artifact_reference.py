"""Cryptographically authorized, job-bound ArtifactReference v2."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .artifact_reference import (
    ArtifactReferenceError,
    VersionedObjectReader,
    authorization_binding_hash,
    read_authorized_artifact,
)
from .result_persistence import stable_hash


SIGNED_ARTIFACT_REFERENCE_SCHEMA_VERSION = "a2.artifact_reference.v2"
SIGNED_ARTIFACT_RESOLUTION_SCHEMA_VERSION = "a2.artifact_reference_resolution.v2"
SIGNATURE_ALGORITHM = "ed25519"
DEFAULT_MAX_TTL_SECONDS = 900
SCOPE_FIELDS = ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")


@dataclass(frozen=True)
class ArtifactVerificationKey:
    issuer: str
    key_id: str
    public_key: Ed25519PublicKey
    status: str = "active"
    valid_from: str = "1970-01-01T00:00:00Z"
    valid_until: str = "9999-12-31T23:59:59Z"
    compromised_at: str | None = None


KeyResolver = Callable[[str, str], ArtifactVerificationKey]


LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS a2_artifact_reference_consumptions (
  nonce_hash TEXT PRIMARY KEY,
  reference_id_hash TEXT NOT NULL,
  authorization_hash TEXT NOT NULL,
  issuer_hash TEXT NOT NULL,
  key_id_hash TEXT NOT NULL,
  audience_hash TEXT NOT NULL,
  subject_hash TEXT NOT NULL,
  evaluation_job_id_hash TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('reserved', 'consumed', 'failed', 'revoked')),
  reserved_at TEXT NOT NULL,
  completed_at TEXT,
  failure_class TEXT,
  receipt_hash TEXT NOT NULL,
  public_safe INTEGER NOT NULL CHECK (public_safe = 1)
);

CREATE TABLE IF NOT EXISTS a2_artifact_reference_revocations (
  revocation_id TEXT PRIMARY KEY,
  revocation_type TEXT NOT NULL CHECK (
    revocation_type IN ('reference', 'job', 'issuer_key', 'tenant_project')
  ),
  target_hash TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  revoked_at TEXT NOT NULL,
  UNIQUE(revocation_type, target_hash, tenant_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_a2_artifact_reference_consumptions_scope
  ON a2_artifact_reference_consumptions(tenant_id, project_id, status, reserved_at);
CREATE INDEX IF NOT EXISTS idx_a2_artifact_reference_revocations_target
  ON a2_artifact_reference_revocations(revocation_type, target_hash, tenant_id, project_id);
"""


class ArtifactAuthorizationLedger:
    """SQLite reference ledger for atomic single-use and revocation semantics."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.executescript(LEDGER_DDL)

    def revoke(
        self,
        *,
        revocation_type: str,
        target: str,
        scope: Mapping[str, str],
        reason_code: str,
        revoked_at: str,
    ) -> str:
        if revocation_type not in {"reference", "job", "issuer_key", "tenant_project"}:
            raise ValueError("unsupported artifact authorization revocation type")
        target_hash = stable_hash(target)
        revocation_id = stable_hash(
            {
                "revocation_type": revocation_type,
                "target_hash": target_hash,
                "tenant_scope": _scope(scope),
                "reason_code": reason_code,
                "revoked_at": revoked_at,
            }
        )
        self.connection.execute(
            """
            INSERT OR IGNORE INTO a2_artifact_reference_revocations (
              revocation_id, revocation_type, target_hash,
              organization_id, tenant_id, workspace_id, project_id, environment_id,
              reason_code, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revocation_id,
                revocation_type,
                target_hash,
                *(_scope(scope)[field] for field in SCOPE_FIELDS),
                reason_code,
                revoked_at,
            ),
        )
        self.connection.commit()
        return revocation_id

    def reserve(
        self,
        reference: Mapping[str, Any],
        *,
        authorization_hash: str,
        reserved_at: str,
    ) -> dict[str, Any]:
        scope = _scope(reference.get("tenant_scope"))
        nonce_hash = stable_hash(str(reference["nonce"]))
        receipt_core = {
            "nonce_hash": nonce_hash,
            "reference_id_hash": stable_hash(str(reference["reference_id"])),
            "authorization_hash": authorization_hash,
            "evaluation_job_id_hash": stable_hash(str(reference["evaluation_job_id"])),
            "status": "reserved",
            "reserved_at": reserved_at,
        }
        receipt_hash = stable_hash(receipt_core)
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            blockers = self._revocation_blockers(reference, scope)
            if blockers:
                raise ArtifactReferenceError(blockers, {})
            self.connection.execute(
                """
                INSERT INTO a2_artifact_reference_consumptions (
                  nonce_hash, reference_id_hash, authorization_hash,
                  issuer_hash, key_id_hash, audience_hash, subject_hash,
                  evaluation_job_id_hash,
                  organization_id, tenant_id, workspace_id, project_id, environment_id,
                  status, reserved_at, receipt_hash, public_safe
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?, 1)
                """,
                (
                    nonce_hash,
                    receipt_core["reference_id_hash"],
                    authorization_hash,
                    stable_hash(str(reference["issuer"])),
                    stable_hash(str(reference["key_id"])),
                    stable_hash(str(reference["audience"])),
                    stable_hash(str(reference["subject"])),
                    receipt_core["evaluation_job_id_hash"],
                    *(scope[field] for field in SCOPE_FIELDS),
                    reserved_at,
                    receipt_hash,
                ),
            )
            self.connection.commit()
        except sqlite3.IntegrityError as error:
            self.connection.rollback()
            raise ArtifactReferenceError(["authorization_replay_detected"], {}) from error
        except ArtifactReferenceError:
            self.connection.rollback()
            raise
        except Exception:
            self.connection.rollback()
            raise
        return {**receipt_core, "receipt_hash": receipt_hash}

    def complete(self, nonce: str, *, completed_at: str, status: str, failure_class: str = "") -> str:
        if status not in {"consumed", "failed"}:
            raise ValueError("unsupported artifact authorization completion status")
        nonce_hash = stable_hash(nonce)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT status, receipt_hash FROM a2_artifact_reference_consumptions WHERE nonce_hash = ?",
                (nonce_hash,),
            ).fetchone()
            if row is None or row[0] != "reserved":
                raise ValueError("artifact authorization is not reserved")
            completion_hash = stable_hash(
                {
                    "nonce_hash": nonce_hash,
                    "reservation_receipt_hash": row[1],
                    "status": status,
                    "completed_at": completed_at,
                    "failure_class": failure_class,
                }
            )
            self.connection.execute(
                """
                UPDATE a2_artifact_reference_consumptions
                SET status = ?, completed_at = ?, failure_class = ?, receipt_hash = ?
                WHERE nonce_hash = ? AND status = 'reserved'
                """,
                (status, completed_at, failure_class or None, completion_hash, nonce_hash),
            )
            self.connection.commit()
            return completion_hash
        except Exception:
            self.connection.rollback()
            raise

    def _revocation_blockers(
        self,
        reference: Mapping[str, Any],
        scope: Mapping[str, str],
    ) -> list[str]:
        targets = {
            "reference": str(reference["reference_id"]),
            "job": str(reference["evaluation_job_id"]),
            "issuer_key": f"{reference['issuer']}:{reference['key_id']}",
            "tenant_project": f"{scope['tenant_id']}:{scope['project_id']}",
        }
        blockers: list[str] = []
        for revocation_type, target in targets.items():
            row = self.connection.execute(
                """
                SELECT 1 FROM a2_artifact_reference_revocations
                WHERE revocation_type = ? AND target_hash = ?
                  AND tenant_id = ? AND project_id = ?
                """,
                (revocation_type, stable_hash(target), scope["tenant_id"], scope["project_id"]),
            ).fetchone()
            if row is not None:
                blockers.append(f"authorization_revoked:{revocation_type}")
        return blockers


def sign_artifact_reference(
    reference: Mapping[str, Any],
    *,
    private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    unsigned = dict(reference)
    unsigned.pop("signature", None)
    if unsigned.get("schema_version") != SIGNED_ARTIFACT_REFERENCE_SCHEMA_VERSION:
        raise ValueError("signed ArtifactReference must use v2 schema")
    unsigned["algorithm"] = SIGNATURE_ALGORITHM
    signature = private_key.sign(_canonical_json(unsigned))
    return {**unsigned, "signature": _b64url(signature)}


def read_signed_artifact(
    reference: Mapping[str, Any],
    *,
    reader: VersionedObjectReader,
    key_resolver: KeyResolver,
    ledger: ArtifactAuthorizationLedger,
    expected_scope: Mapping[str, str],
    expected_purpose: str,
    expected_issuer: str,
    expected_audience: str,
    expected_subject: str,
    expected_evaluation_job_id: str,
    now: str,
    max_bytes: int,
    max_ttl_seconds: int = DEFAULT_MAX_TTL_SECONDS,
) -> tuple[bytes, dict[str, Any]]:
    blockers, key = _verify_authorization(
        reference,
        key_resolver=key_resolver,
        expected_scope=expected_scope,
        expected_purpose=expected_purpose,
        expected_issuer=expected_issuer,
        expected_audience=expected_audience,
        expected_subject=expected_subject,
        expected_evaluation_job_id=expected_evaluation_job_id,
        now=now,
        max_ttl_seconds=max_ttl_seconds,
    )
    authorization_hash = stable_hash(_unsigned(reference))
    if blockers:
        raise ArtifactReferenceError(
            blockers,
            _security_resolution(reference, blockers, authorization_hash=authorization_hash),
        )
    try:
        reservation = ledger.reserve(
            reference,
            authorization_hash=authorization_hash,
            reserved_at=now,
        )
    except ArtifactReferenceError as error:
        blockers = error.blockers
        raise ArtifactReferenceError(
            blockers,
            _security_resolution(reference, blockers, authorization_hash=authorization_hash),
        ) from None

    v1 = _v1_compatibility_reference(reference)
    try:
        content, object_resolution = read_authorized_artifact(
            v1,
            reader=reader,
            expected_scope=expected_scope,
            expected_purpose=expected_purpose,
            now=now,
            max_bytes=max_bytes,
        )
    except ArtifactReferenceError as error:
        ledger.complete(
            str(reference["nonce"]),
            completed_at=now,
            status="failed",
            failure_class=error.blockers[0] if error.blockers else "artifact_read_failed",
        )
        raise ArtifactReferenceError(
            error.blockers,
            _merge_resolution(
                reference,
                error.resolution,
                error.blockers,
                authorization_hash=authorization_hash,
                reservation=reservation,
                key=key,
                consumption_status="failed",
            ),
        ) from None

    completion_hash = ledger.complete(
        str(reference["nonce"]),
        completed_at=now,
        status="consumed",
    )
    return content, _merge_resolution(
        reference,
        object_resolution,
        [],
        authorization_hash=authorization_hash,
        reservation={**reservation, "completion_hash": completion_hash},
        key=key,
        consumption_status="consumed",
    )


def _verify_authorization(
    reference: Mapping[str, Any],
    *,
    key_resolver: KeyResolver,
    expected_scope: Mapping[str, str],
    expected_purpose: str,
    expected_issuer: str,
    expected_audience: str,
    expected_subject: str,
    expected_evaluation_job_id: str,
    now: str,
    max_ttl_seconds: int,
) -> tuple[list[str], ArtifactVerificationKey | None]:
    blockers: list[str] = []
    required = {
        "schema_version", "reference_id", "tenant_scope", "artifact_id", "storage_provider",
        "container_ref", "object_ref", "object_version", "content_hash", "size_bytes",
        "media_type", "purpose", "issuer", "subject", "audience", "evaluation_job_id",
        "nonce", "issued_at", "not_before", "expires_at", "algorithm", "key_id", "signature",
    }
    if set(reference) != required:
        blockers.append("signed_reference_fields_invalid")
    if reference.get("schema_version") != SIGNED_ARTIFACT_REFERENCE_SCHEMA_VERSION:
        blockers.append("reference_schema_unsupported")
    if reference.get("algorithm") != SIGNATURE_ALGORITHM:
        blockers.append("signature_algorithm_unsupported")
    comparisons = {
        "issuer_mismatch": (reference.get("issuer"), expected_issuer),
        "audience_mismatch": (reference.get("audience"), expected_audience),
        "subject_mismatch": (reference.get("subject"), expected_subject),
        "evaluation_job_mismatch": (
            reference.get("evaluation_job_id"),
            expected_evaluation_job_id,
        ),
        "purpose_mismatch": (reference.get("purpose"), expected_purpose),
    }
    blockers.extend(name for name, values in comparisons.items() if values[0] != values[1])
    reference_scope = _scope(reference.get("tenant_scope"))
    expected_scope_values = _scope(expected_scope)
    if not all(reference_scope.values()):
        blockers.append("reference_tenant_scope_incomplete")
    if not all(expected_scope_values.values()):
        blockers.append("expected_tenant_scope_incomplete")
    if reference_scope != expected_scope_values:
        blockers.append("tenant_scope_mismatch")

    current = _parse_time(now, "evaluation_time", blockers)
    issued = _parse_time(reference.get("issued_at"), "issued_at", blockers)
    not_before = _parse_time(reference.get("not_before"), "not_before", blockers)
    expires = _parse_time(reference.get("expires_at"), "expires_at", blockers)
    if current and not_before and current < not_before:
        blockers.append("reference_not_yet_valid")
    if current and expires and current >= expires:
        blockers.append("reference_expired")
    if issued and not_before and not_before < issued:
        blockers.append("reference_validity_order_invalid")
    if issued and expires:
        if expires <= issued:
            blockers.append("reference_lifetime_invalid")
        elif expires - issued > timedelta(seconds=max_ttl_seconds):
            blockers.append("reference_ttl_exceeded")

    key: ArtifactVerificationKey | None = None
    try:
        key = key_resolver(str(reference.get("issuer") or ""), str(reference.get("key_id") or ""))
    except Exception:
        blockers.append("verification_key_unavailable")
    if key is not None:
        if key.issuer != reference.get("issuer") or key.key_id != reference.get("key_id"):
            blockers.append("verification_key_identity_mismatch")
        if key.status != "active":
            blockers.append("verification_key_inactive")
        valid_from = _parse_time(key.valid_from, "key_valid_from", blockers)
        valid_until = _parse_time(key.valid_until, "key_valid_until", blockers)
        compromised_at = (
            _parse_time(key.compromised_at, "key_compromised_at", blockers)
            if key.compromised_at
            else None
        )
        if issued and valid_from and issued < valid_from:
            blockers.append("verification_key_not_yet_valid")
        if issued and valid_until and issued >= valid_until:
            blockers.append("verification_key_expired")
        if issued and compromised_at and issued >= compromised_at:
            blockers.append("verification_key_compromised")
        try:
            key.public_key.verify(_b64url_decode(str(reference.get("signature") or "")), _canonical_json(_unsigned(reference)))
        except (InvalidSignature, ValueError, TypeError):
            blockers.append("signature_invalid")
    return sorted(set(blockers)), key


def _v1_compatibility_reference(reference: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "reference_id", "tenant_scope", "artifact_id", "storage_provider", "container_ref",
        "object_ref", "object_version", "content_hash", "size_bytes", "media_type",
        "purpose", "issued_at", "expires_at",
    )
    result = {"schema_version": "a2.artifact_reference.v1"}
    result.update({field: reference[field] for field in fields})
    result["authorization_binding_hash"] = authorization_binding_hash(result)
    return result


def _merge_resolution(
    reference: Mapping[str, Any],
    object_resolution: Mapping[str, Any],
    blockers: list[str],
    *,
    authorization_hash: str,
    reservation: Mapping[str, Any],
    key: ArtifactVerificationKey | None,
    consumption_status: str,
) -> dict[str, Any]:
    core = {
        **{key_name: value for key_name, value in object_resolution.items() if key_name != "resolution_hash"},
        "schema_version": SIGNED_ARTIFACT_RESOLUTION_SCHEMA_VERSION,
        "issuer_hash": stable_hash(str(reference.get("issuer") or "")),
        "key_id_hash": stable_hash(str(reference.get("key_id") or "")),
        "algorithm": str(reference.get("algorithm") or ""),
        "audience_hash": stable_hash(str(reference.get("audience") or "")),
        "subject_hash": stable_hash(str(reference.get("subject") or "")),
        "evaluation_job_id_hash": stable_hash(str(reference.get("evaluation_job_id") or "")),
        "nonce_hash": stable_hash(str(reference.get("nonce") or "")),
        "authorization_hash": authorization_hash,
        "signature_verified": key is not None and not blockers,
        "revocation_checked": True,
        "consumption_status": consumption_status,
        "authorization_receipt_hash": str(
            reservation.get("completion_hash") or reservation.get("receipt_hash") or ""
        ),
        "blockers": sorted(set(blockers)),
        "status": "verified" if not blockers else "blocked",
    }
    return {**core, "resolution_hash": stable_hash(core)}


def _security_resolution(
    reference: Mapping[str, Any],
    blockers: list[str],
    *,
    authorization_hash: str,
) -> dict[str, Any]:
    scope = _scope(reference.get("tenant_scope"))
    core = {
        "schema_version": SIGNED_ARTIFACT_RESOLUTION_SCHEMA_VERSION,
        "reference_id_hash": stable_hash(str(reference.get("reference_id") or "")),
        "artifact_id": str(reference.get("artifact_id") or ""),
        "tenant_scope": scope,
        "storage_provider": str(reference.get("storage_provider") or ""),
        "container_ref_hash": stable_hash(str(reference.get("container_ref") or "")),
        "object_ref_hash": stable_hash(str(reference.get("object_ref") or "")),
        "expected_object_version_hash": stable_hash(str(reference.get("object_version") or "")),
        "observed_object_version_hash": "",
        "expected_content_hash": str(reference.get("content_hash") or ""),
        "actual_content_hash": "",
        "expected_size_bytes": reference.get("size_bytes") if isinstance(reference.get("size_bytes"), int) else None,
        "actual_size_bytes": None,
        "purpose": str(reference.get("purpose") or ""),
        "reader_id": "",
        "reader_version": "",
        "read_performed": False,
        "status": "blocked",
        "blockers": sorted(set(blockers)),
        "raw_content_included": False,
        "secret_material_included": False,
        "issuer_hash": stable_hash(str(reference.get("issuer") or "")),
        "key_id_hash": stable_hash(str(reference.get("key_id") or "")),
        "algorithm": str(reference.get("algorithm") or ""),
        "audience_hash": stable_hash(str(reference.get("audience") or "")),
        "subject_hash": stable_hash(str(reference.get("subject") or "")),
        "evaluation_job_id_hash": stable_hash(str(reference.get("evaluation_job_id") or "")),
        "nonce_hash": stable_hash(str(reference.get("nonce") or "")),
        "authorization_hash": authorization_hash,
        "signature_verified": False,
        "revocation_checked": False,
        "consumption_status": "not_reserved",
        "authorization_receipt_hash": "",
    }
    return {**core, "resolution_hash": stable_hash(core)}


def _unsigned(reference: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in reference.items() if key != "signature"}


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


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


def _scope(value: Any) -> dict[str, str]:
    source = value if isinstance(value, Mapping) else {}
    return {field: str(source.get(field) or "") for field in SCOPE_FIELDS}
