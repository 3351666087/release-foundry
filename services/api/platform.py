from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from ashr_clone.storage import (
    LocalFilesystemObjectStorage,
    ObjectStorageContractError,
    build_object_manifest,
    scoped_object_key,
    verify_object_bytes,
)

from .runtime import JsonDict, ValidationError, _jsonable, _utc_now

PLATFORM_SCHEMA_VERSION = "ashr.clone.saas_platform.v1"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _suffix_for_content_type(content_type: str) -> str:
    mapping = {
        "application/json": ".json",
        "text/plain": ".txt",
        "text/markdown": ".md",
        "text/csv": ".csv",
    }
    return mapping.get(str(content_type).split(";", 1)[0].strip().lower(), ".bin")


SAAS_TABLES: dict[str, dict[str, Any]] = {
    "organizations": {"primary_key": "organization_id", "tenant_scoped": False, "columns": ["organization_id", "name", "status", "created_at"]},
    "workspaces": {"primary_key": "workspace_id", "tenant_scoped": True, "columns": ["organization_id", "workspace_id", "name", "status", "created_at"]},
    "projects": {"primary_key": "project_id", "tenant_scoped": True, "columns": ["organization_id", "workspace_id", "project_id", "name", "environment", "status", "created_at"]},
    "environments": {"primary_key": "environment_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "environment_id", "name", "kind", "created_at"]},
    "datasets": {"primary_key": "dataset_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "dataset_id", "name", "case_count", "schema_version", "created_at"]},
    "runs": {"primary_key": "run_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "dataset_id", "run_id", "status", "agent_ref", "created_at", "completed_at"]},
    "case_results": {"primary_key": "case_result_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "run_id", "case_result_id", "case_id", "status", "grade_status", "created_at"]},
    "trace_events": {"primary_key": "trace_event_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "run_id", "trace_event_id", "event_type", "event_time", "payload_sha256"]},
    "observations": {"primary_key": "observation_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "run_id", "observation_id", "type", "payload_sha256", "created_at"]},
    "artifacts": {"primary_key": "artifact_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "run_id", "artifact_id", "content_type", "size_bytes", "sha256", "redaction_status", "created_at"]},
    "evidence_bundles": {"primary_key": "bundle_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "run_id", "bundle_id", "artifact_count", "sha256", "created_at"]},
    "api_keys": {"primary_key": "key_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "key_id", "prefix", "secret_hash_sha256", "scopes", "status", "created_at", "revoked_at"]},
    "webhook_endpoints": {"primary_key": "webhook_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "webhook_id", "url", "events", "secret_hash_sha256", "status", "created_at"]},
    "webhook_deliveries": {"primary_key": "delivery_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "webhook_id", "delivery_id", "event_type", "payload_sha256", "status", "created_at"]},
    "usage_ledger": {"primary_key": "usage_event_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "usage_event_id", "operation", "units", "billing_period", "created_at"]},
    "quota_policies": {"primary_key": "quota_policy_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "quota_policy_id", "operation", "limit", "period", "created_at"]},
    "billing_accounts": {"primary_key": "billing_account_id", "tenant_scoped": True, "columns": ["organization_id", "billing_account_id", "plan", "status", "billing_period", "created_at"]},
    "integrations": {"primary_key": "integration_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "integration_id", "provider", "status", "created_at"]},
    "audit_log": {"primary_key": "audit_event_id", "tenant_scoped": True, "columns": ["organization_id", "project_id", "audit_event_id", "actor_id", "action", "target_id", "created_at"]},
}


def platform_schema_manifest() -> JsonDict:
    tables: dict[str, JsonDict] = {}
    indexes: list[JsonDict] = []
    for name, table in SAAS_TABLES.items():
        columns = list(table["columns"])
        tenant_scoped = bool(table["tenant_scoped"])
        primary_key = str(table["primary_key"])
        tables[name] = {
            "name": name,
            "primary_key": primary_key,
            "tenant_scoped": tenant_scoped,
            "columns": columns,
            "required_columns": [primary_key, *(["organization_id"] if tenant_scoped else [])],
        }
        indexes.append({"name": f"idx_{name}_{primary_key}", "table": name, "columns": [primary_key], "unique": True})
        if tenant_scoped:
            scoped_columns = ["organization_id", primary_key]
            if "project_id" in columns:
                scoped_columns = ["organization_id", "project_id", primary_key]
            indexes.append({"name": f"idx_{name}_tenant_scope", "table": name, "columns": scoped_columns, "unique": False})
    return {
        "schema_version": PLATFORM_SCHEMA_VERSION,
        "metadata": {"local_only": True, "ashr_api_used": False, "generated_at": _utc_now()},
        "tables": tables,
        "indexes": indexes,
        "invariants": [
            "all project-owned tables carry organization_id",
            "all project-owned tables with project_id have tenant scoped indexes",
            "public artifacts never include raw secret or raw payload bytes",
            "webhook public views expose secret_hash_present only",
        ],
    }


def platform_sql_migration_text() -> str:
    lines = ["-- Ashr++ local SaaS platform DB-shaped migration", f"-- schema_version: {PLATFORM_SCHEMA_VERSION}"]
    for name, table in SAAS_TABLES.items():
        col_defs = []
        for col in table["columns"]:
            typ = "INTEGER" if col in {"case_count", "size_bytes", "units", "limit", "artifact_count"} else "TEXT"
            suffix = " PRIMARY KEY" if col == table["primary_key"] else ""
            col_defs.append(f"  {col} {typ}{suffix}")
        lines.append(f"CREATE TABLE IF NOT EXISTS {name} (\n" + ",\n".join(col_defs) + "\n);")
    for index in platform_schema_manifest()["indexes"]:
        unique = "UNIQUE " if index["unique"] else ""
        cols = ", ".join(index["columns"])
        lines.append(f"CREATE {unique}INDEX IF NOT EXISTS {index['name']} ON {index['table']} ({cols});")
    return "\n".join(lines) + "\n"


@dataclass(slots=True)
class LocalObjectStore:
    artifacts: dict[str, JsonDict] = field(default_factory=dict)
    signed_urls: dict[str, JsonDict] = field(default_factory=dict)
    evidence_bundles: dict[str, JsonDict] = field(default_factory=dict)
    object_root: str | Path | None = None

    def put_artifact(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str | None,
        content: bytes | str,
        content_type: str,
        artifact_id: str | None = None,
        redaction_status: str = "redacted",
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        if redaction_status not in {"redacted", "public", "private", "hash_only"}:
            raise ValidationError("redaction_status must be redacted, public, private, or hash_only")
        raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        digest = hashlib.sha256(raw).hexdigest()
        artifact_id = artifact_id or _new_id("artifact")
        if artifact_id in self.artifacts:
            raise ValidationError(f"artifact already exists: {artifact_id}")
        suffix = _suffix_for_content_type(content_type)
        try:
            if self.object_root is not None:
                object_manifest = LocalFilesystemObjectStorage(self.object_root).write_object(
                    tenant_id=str(tenant_id),
                    project_id=str(project_id),
                    run_id=str(run_id or "runless"),
                    object_id=artifact_id,
                    content=raw,
                    content_type=content_type,
                    category="artifacts",
                    suffix=suffix,
                    metadata={"redaction_status": redaction_status, **dict(metadata or {})},
                )
            else:
                object_key = scoped_object_key(
                    tenant_id=str(tenant_id),
                    project_id=str(project_id),
                    run_id=str(run_id or "runless"),
                    object_id=artifact_id,
                    category="artifacts",
                    suffix=suffix,
                )
                object_manifest = build_object_manifest(
                    backend="local-filesystem",
                    object_key=object_key,
                    tenant_id=str(tenant_id),
                    project_id=str(project_id),
                    run_id=str(run_id or "runless"),
                    object_id=artifact_id,
                    content_type=content_type,
                    size_bytes=len(raw),
                    sha256=digest,
                    metadata={"redaction_status": redaction_status, **dict(metadata or {})},
                )
        except ObjectStorageContractError as exc:
            raise ValidationError(str(exc)) from exc
        record = {
            "schema_version": PLATFORM_SCHEMA_VERSION,
            "artifact_id": artifact_id,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "run_id": run_id,
            "content_type": str(content_type),
            "size_bytes": len(raw),
            "sha256": digest,
            "redaction_status": redaction_status,
            "object_key": object_manifest["object_key"],
            "storage_uri": object_manifest["backend_refs"]["storage_uri"],
            "object_storage": object_manifest,
            "write_readback_verified": bool(object_manifest.get("write_readback_verification", {}).get("verified")) if self.object_root is not None else None,
            "raw_payload_included": False,
            "secret_value_present": False,
            "metadata": _jsonable(dict(metadata or {})),
            "created_at": _utc_now(),
        }
        self.artifacts[artifact_id] = record
        return _jsonable(record)

    def create_signed_upload_url(self, *, tenant_id: str, project_id: str, artifact_id: str | None = None, expires_in_seconds: int = 900) -> JsonDict:
        if expires_in_seconds <= 0 or expires_in_seconds > 86_400:
            raise ValidationError("expires_in_seconds must be between 1 and 86400")
        artifact_id = artifact_id or _new_id("artifact")
        token = hashlib.sha256(f"{tenant_id}:{project_id}:{artifact_id}:{uuid4().hex}".encode("utf-8")).hexdigest()[:32]
        url_id = _new_id("upload_url")
        record = {
            "schema_version": PLATFORM_SCHEMA_VERSION,
            "upload_url_id": url_id,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "artifact_id": artifact_id,
            "method": "PUT",
            "url": f"local://object-store/{artifact_id}?signature={token}",
            "expires_in_seconds": int(expires_in_seconds),
            "created_at": _utc_now(),
            "local_only": True,
        }
        self.signed_urls[url_id] = record
        return _jsonable(record)

    def public_manifest(self, tenant_id: str, project_id: str) -> JsonDict:
        artifacts = [item for item in self.artifacts.values() if item.get("tenant_id") == str(tenant_id) and item.get("project_id") == str(project_id)]
        bundles = [item for item in self.evidence_bundles.values() if item.get("tenant_id") == str(tenant_id) and item.get("project_id") == str(project_id)]
        return {"schema_version": PLATFORM_SCHEMA_VERSION, "tenant_id": str(tenant_id), "project_id": str(project_id), "artifacts": _jsonable(artifacts), "evidence_bundles": _jsonable(bundles)}

    def put_evidence_bundle(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        packet: Mapping[str, Any],
        bundle_id: str | None = None,
        storage_prefix: str = "evidence-bundles",
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        packet_payload = _jsonable(dict(packet))
        verification = verify_release_evidence_packet(packet_payload)
        if not verification["verified"]:
            raise ValidationError("release evidence packet must verify before storage")
        if str(packet_payload.get("tenant_id")) != str(tenant_id) or str(packet_payload.get("project_id")) != str(project_id) or str(packet_payload.get("run_id")) != str(run_id):
            raise ValidationError("release evidence packet tenant/project/run does not match storage target")
        bundle_id = bundle_id or _new_id("bundle")
        if bundle_id in self.evidence_bundles:
            raise ValidationError(f"evidence bundle already exists: {bundle_id}")
        encoded = json.dumps(packet_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        bundle_sha256 = hashlib.sha256(encoded).hexdigest()
        try:
            object_key = scoped_object_key(tenant_id=str(tenant_id), project_id=str(project_id), run_id=str(run_id), object_id=bundle_id, category=storage_prefix, suffix=".json")
            if self.object_root is not None:
                object_manifest = LocalFilesystemObjectStorage(self.object_root).write_object(
                    tenant_id=str(tenant_id),
                    project_id=str(project_id),
                    run_id=str(run_id),
                    object_id=bundle_id,
                    content=encoded,
                    content_type="application/json",
                    category=storage_prefix,
                    suffix=".json",
                    metadata={"packet_id": packet_payload.get("packet_id"), **dict(metadata or {})},
                )
            else:
                object_manifest = build_object_manifest(
                    backend="local-filesystem",
                    object_key=object_key,
                    tenant_id=str(tenant_id),
                    project_id=str(project_id),
                    run_id=str(run_id),
                    object_id=bundle_id,
                    content_type="application/json",
                    size_bytes=len(encoded),
                    sha256=bundle_sha256,
                    metadata={"packet_id": packet_payload.get("packet_id"), **dict(metadata or {})},
                )
        except ObjectStorageContractError as exc:
            raise ValidationError(str(exc)) from exc
        record = {
            "schema_version": "ashr.clone.evidence_bundle_object.v1",
            "bundle_id": bundle_id,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "run_id": str(run_id),
            "packet_id": packet_payload.get("packet_id"),
            "packet_sha256": verification.get("packet_sha256"),
            "bundle_sha256": bundle_sha256,
            "object_key": object_key,
            "storage_uri": object_manifest["backend_refs"]["storage_uri"],
            "object_storage": object_manifest,
            "content_type": "application/json",
            "size_bytes": len(encoded),
            "evidence_item_count": len(_list_or_empty(packet_payload.get("evidence_items"))),
            "raw_payload_included": False,
            "secret_value_present": False,
            "write_readback_verified": bool(object_manifest.get("write_readback_verification", {}).get("verified")) if self.object_root is not None else None,
            "verification": verification,
            "metadata": _jsonable(dict(metadata or {})),
            "created_at": _utc_now(),
        }
        self.evidence_bundles[bundle_id] = record
        return _jsonable(record)

    def verify_stored_evidence_bundle(self, *, tenant_id: str, project_id: str, bundle_id: str, expected_packet_sha256: str | None = None) -> JsonDict:
        record = self.evidence_bundles.get(bundle_id)
        failures: list[JsonDict] = []
        if record is None:
            raise ValidationError(f"evidence bundle not found: {bundle_id}")
        if record.get("tenant_id") != str(tenant_id) or record.get("project_id") != str(project_id):
            failures.append({"reason": "tenant_project_mismatch"})
        if expected_packet_sha256 is not None and record.get("packet_sha256") != expected_packet_sha256:
            failures.append({"reason": "packet_sha256_mismatch", "expected": expected_packet_sha256, "actual": record.get("packet_sha256")})
        if record.get("raw_payload_included"):
            failures.append({"reason": "raw_payload_included"})
        if record.get("secret_value_present"):
            failures.append({"reason": "secret_value_present"})
        if not record.get("object_key") or not str(record.get("storage_uri", "")).startswith("local://object-store/"):
            failures.append({"reason": "storage_reference_missing"})
        object_manifest = record.get("object_storage") if isinstance(record.get("object_storage"), Mapping) else None
        if object_manifest is None:
            failures.append({"reason": "object_manifest_missing"})
        elif self.object_root is not None:
            try:
                readback = LocalFilesystemObjectStorage(self.object_root).verify_object(object_manifest)
            except (OSError, ObjectStorageContractError) as exc:
                readback = {"verified": False, "failures": [{"reason": "readback_failed", "detail": str(exc)}]}
            if not readback.get("verified"):
                failures.append({"reason": "object_readback_mismatch", "details": readback.get("failures", [])})
        elif object_manifest is not None:
            readback = verify_object_bytes(object_manifest, b"") if object_manifest.get("size_bytes") == 0 else None
        else:
            readback = None
        return {
            "schema_version": "ashr.clone.evidence_bundle_object_verification.v1",
            "verified": not failures,
            "bundle_id": bundle_id,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "packet_sha256": record.get("packet_sha256"),
            "bundle_sha256": record.get("bundle_sha256"),
            "object_key": record.get("object_key"),
            "storage_uri": record.get("storage_uri"),
            "object_storage": object_manifest,
            "readback_verification": readback,
            "failures": failures,
        }


@dataclass(slots=True)
class WebhookRegistry:
    endpoints: dict[str, JsonDict] = field(default_factory=dict)
    _secrets: dict[str, str] = field(default_factory=dict)
    deliveries: dict[str, JsonDict] = field(default_factory=dict)

    def register_endpoint(self, *, tenant_id: str, project_id: str, url: str, events: Sequence[str], webhook_id: str | None = None) -> JsonDict:
        if not str(url).startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValidationError("webhook url must be https or localhost for local tests")
        normalized_events = [str(event) for event in events]
        if not normalized_events:
            raise ValidationError("webhook events must not be empty")
        webhook_id = webhook_id or _new_id("webhook")
        secret = f"whsec_local_{uuid4().hex}"
        secret_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        record = {
            "schema_version": PLATFORM_SCHEMA_VERSION,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "webhook_id": webhook_id,
            "url": str(url),
            "events": normalized_events,
            "status": "active",
            "secret_hash_present": True,
            "secret_value_present": False,
            "secret_hash_sha256": secret_hash,
            "created_at": _utc_now(),
        }
        self.endpoints[webhook_id] = record
        self._secrets[webhook_id] = secret
        return _public_webhook(record)

    def deliver(self, *, tenant_id: str, project_id: str, event_type: str, payload: Mapping[str, Any], webhook_id: str | None = None) -> JsonDict:
        endpoints = [record for record in self.endpoints.values() if record.get("tenant_id") == str(tenant_id) and record.get("project_id") == str(project_id) and record.get("status") == "active"]
        if webhook_id is not None:
            endpoints = [record for record in endpoints if record.get("webhook_id") == webhook_id]
        payload_bytes = json.dumps(_jsonable(dict(payload)), sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload_sha = hashlib.sha256(payload_bytes).hexdigest()
        deliveries: list[JsonDict] = []
        for endpoint in endpoints:
            if event_type not in endpoint.get("events", []) and "*" not in endpoint.get("events", []):
                continue
            delivery_id = _new_id("delivery")
            secret = self._secrets[str(endpoint["webhook_id"])]
            signature_digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
            signed_payload_sha = hashlib.sha256(f"{payload_sha}:{signature_digest}".encode("utf-8")).hexdigest()
            record = {
                "schema_version": PLATFORM_SCHEMA_VERSION,
                "tenant_id": str(tenant_id),
                "project_id": str(project_id),
                "webhook_id": endpoint["webhook_id"],
                "delivery_id": delivery_id,
                "event_type": str(event_type),
                "payload_sha256": payload_sha,
                "raw_payload_included": False,
                "status": "simulated",
                "headers": {"x-ashr-event": str(event_type), "x-ashr-signature-sha256": "present"},
                "signature_present": True,
                "signature_algorithm": "hmac-sha256",
                "signed_payload_sha256": signed_payload_sha,
                "created_at": _utc_now(),
            }
            self.deliveries[delivery_id] = record
            deliveries.append(record)
        return {"schema_version": PLATFORM_SCHEMA_VERSION, "tenant_id": str(tenant_id), "project_id": str(project_id), "event_type": str(event_type), "deliveries": _jsonable(deliveries)}


def _public_webhook(record: Mapping[str, Any]) -> JsonDict:
    return {
        "schema_version": PLATFORM_SCHEMA_VERSION,
        "tenant_id": record.get("tenant_id"),
        "project_id": record.get("project_id"),
        "webhook_id": record.get("webhook_id"),
        "url": record.get("url"),
        "events": list(record.get("events", [])),
        "status": record.get("status"),
        "secret_hash_present": bool(record.get("secret_hash_present")),
        "secret_value_present": False,
        "created_at": record.get("created_at"),
    }


def usage_billing_rollup(usage_events: Sequence[Mapping[str, Any]], *, tenant_id: str, project_id: str, billing_period: str) -> JsonDict:
    totals: dict[str, int] = {}
    for event in usage_events:
        if str(event.get("tenant_id")) != str(tenant_id) or str(event.get("project_id")) != str(project_id):
            continue
        operation = str(event.get("operation") or "unknown")
        totals[operation] = totals.get(operation, 0) + int(event.get("units") or 0)
    billable_units = sum(totals.values())
    return {
        "schema_version": PLATFORM_SCHEMA_VERSION,
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "billing_period": str(billing_period),
        "operation_totals": totals,
        "billable_units": billable_units,
        "local_only": True,
        "ashr_api_used": False,
    }


def release_gate_bridge_payload(*, tenant_id: str, project_id: str, run_id: str, lifecycle: Mapping[str, Any], policy: Mapping[str, Any] | None = None) -> JsonDict:
    uploads = lifecycle.get("uploads") if isinstance(lifecycle.get("uploads"), list) else []
    trace_batches = lifecycle.get("trace_batches") if isinstance(lifecycle.get("trace_batches"), list) else []
    policy_payload = dict(policy or {"minimum_trace_batches": 1, "minimum_uploads": 1})
    decision = "pass" if len(uploads) >= int(policy_payload.get("minimum_uploads", 1)) and len(trace_batches) >= int(policy_payload.get("minimum_trace_batches", 1)) else "review"
    return {
        "schema_version": PLATFORM_SCHEMA_VERSION,
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "run_id": str(run_id),
        "target_contract": "A2.release_gate.evaluate",
        "decision_hint": decision,
        "policy": _jsonable(policy_payload),
        "inputs": {
            "run_status": lifecycle.get("run_status"),
            "upload_count": len(uploads),
            "trace_batch_count": len(trace_batches),
            "quota": lifecycle.get("quota"),
        },
        "raw_payload_included": False,
        "created_at": _utc_now(),
    }


def build_release_evidence_packet(
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    lifecycle: Mapping[str, Any],
    artifact_manifest: Mapping[str, Any] | None = None,
    release_gate_result: Mapping[str, Any] | None = None,
    webhook_delivery: Mapping[str, Any] | None = None,
    billing_rollup: Mapping[str, Any] | None = None,
    audit_chain: Mapping[str, Any] | None = None,
    packet_id: str | None = None,
) -> JsonDict:
    """Build a public-safe release evidence packet for A1/A2/A3 handoff.

    The packet is a hash-only bundle: it records run lifecycle counts, artifact
    hashes, release-gate status, webhook delivery hashes, and usage totals while
    intentionally omitting raw run payloads, trace bodies, webhook secrets, and
    private official API responses.
    """

    uploads = _list_or_empty(lifecycle.get("uploads"))
    trace_batches = _list_or_empty(lifecycle.get("trace_batches"))
    artifacts = _list_or_empty((artifact_manifest or {}).get("artifacts"))
    deliveries = _list_or_empty((webhook_delivery or {}).get("deliveries"))
    gate = _jsonable(dict(release_gate_result or {}))
    rollup = _jsonable(dict(billing_rollup or {}))
    chain = _jsonable(dict(audit_chain or {}))
    evidence_items = []
    for artifact in artifacts:
        evidence_items.append(
            {
                "kind": "artifact",
                "id": artifact.get("artifact_id"),
                "sha256": artifact.get("sha256"),
                "content_type": artifact.get("content_type"),
                "size_bytes": artifact.get("size_bytes"),
                "redaction_status": artifact.get("redaction_status"),
            }
        )
    for upload in uploads:
        evidence_items.append({"kind": "run_upload", "id": upload.get("upload_id"), "sha256": upload.get("payload_sha256"), "status": upload.get("status")})
    for batch in trace_batches:
        evidence_items.append({"kind": "trace_batch", "id": batch.get("batch_id"), "observation_count": batch.get("observation_count"), "status": batch.get("status")})
    for delivery in deliveries:
        evidence_items.append({"kind": "webhook_delivery", "id": delivery.get("delivery_id"), "sha256": delivery.get("payload_sha256"), "status": delivery.get("status")})

    payload = {
        "schema_version": "ashr.clone.release_evidence_packet.v1",
        "packet_id": packet_id or _new_id("evidence_packet"),
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "run_id": str(run_id),
        "run_status": lifecycle.get("run_status"),
        "counts": {
            "uploads": len(uploads),
            "trace_batches": len(trace_batches),
            "artifacts": len(artifacts),
            "webhook_deliveries": len(deliveries),
        },
        "release_gate": _release_gate_summary(gate),
        "usage": {
            "billing_period": rollup.get("billing_period"),
            "operation_totals": rollup.get("operation_totals", {}),
            "billable_units": rollup.get("billable_units", 0),
        },
        "audit_chain": {
            "verified": chain.get("verified") if chain else None,
            "event_count": chain.get("event_count", 0),
            "head_audit_event_sha256": chain.get("head_audit_event_sha256"),
            "tail_audit_event_sha256": chain.get("tail_audit_event_sha256"),
            "failure_count": len(chain.get("failures", [])) if isinstance(chain.get("failures"), list) else 0,
        },
        "evidence_items": _jsonable(evidence_items),
        "raw_payload_included": False,
        "secret_value_present": False,
        "ashr_api_used": False,
        "created_at": _utc_now(),
    }
    payload["integrity"] = {"packet_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()}
    return _jsonable(payload)


def verify_release_evidence_packet(packet: Mapping[str, Any]) -> JsonDict:
    payload = _jsonable(dict(packet))
    integrity = payload.get("integrity") if isinstance(payload.get("integrity"), Mapping) else {}
    expected_hash = integrity.get("packet_sha256") if isinstance(integrity, Mapping) else None
    unsigned = {key: value for key, value in payload.items() if key != "integrity"}
    actual_hash = hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode("utf-8")).hexdigest()
    failures = []
    if expected_hash != actual_hash:
        failures.append({"reason": "packet_sha256_mismatch", "expected": expected_hash, "actual": actual_hash})
    redaction = {
        "raw_payload_included": bool(payload.get("raw_payload_included")),
        "secret_value_present": bool(payload.get("secret_value_present")),
    }
    if redaction["raw_payload_included"]:
        failures.append({"reason": "raw_payload_included"})
    if redaction["secret_value_present"]:
        failures.append({"reason": "secret_value_present"})
    failures.extend(_find_suspicious_release_packet_fields(payload))
    return {
        "schema_version": "ashr.clone.release_evidence_packet_verification.v1",
        "verified": not failures,
        "packet_id": payload.get("packet_id"),
        "packet_sha256": expected_hash,
        "actual_packet_sha256": actual_hash,
        "failures": failures,
        "redaction": redaction,
    }


_SUSPICIOUS_RELEASE_PACKET_KEYS = {
    "api_key",
    "authorization",
    "bearer",
    "cookie",
    "set_cookie",
    "password",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "secret",
    "raw_payload",
    "payload",
}


def _find_suspicious_release_packet_fields(value: Any, *, path: str = "$") -> list[JsonDict]:
    failures: list[JsonDict] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            normalized_key = key_text.lower().replace("-", "_")
            item_path = f"{path}.{key_text}"
            if normalized_key in _SUSPICIOUS_RELEASE_PACKET_KEYS:
                failures.append({"reason": "suspicious_field_present", "path": item_path})
            failures.extend(_find_suspicious_release_packet_fields(item, path=item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            failures.extend(_find_suspicious_release_packet_fields(item, path=f"{path}[{index}]"))
    elif isinstance(value, str):
        lowered = value.lower()
        if lowered.startswith("bearer ") or "ashr_api_key=" in lowered:
            failures.append({"reason": "suspicious_value_present", "path": path})
    return failures


def _list_or_empty(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _release_gate_summary(gate: Mapping[str, Any]) -> JsonDict:
    grade = gate.get("grade_result") if isinstance(gate.get("grade_result"), Mapping) else gate
    return {
        "target_contract": gate.get("target_contract") or "A2.release_gate.evaluate",
        "request_id": gate.get("request_id"),
        "idempotency_key": gate.get("idempotency_key"),
        "passed": grade.get("passed") if isinstance(grade, Mapping) else None,
        "score": grade.get("score") if isinstance(grade, Mapping) else None,
        "label": grade.get("label") if isinstance(grade, Mapping) else None,
        "raw_payload_included": False,
    }
