from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qs
from uuid import uuid4

from .runtime import CloudApiService, JsonDict, NotFoundError, ValidationError, _jsonable, _utc_now
from .release_gate_bridge import LocalReleaseGateBridgeClient, evaluate_lifecycle_with_release_gate
from .platform import verify_release_evidence_packet as _verify_release_evidence_packet

CONTROL_PLANE_SCHEMA_VERSION = "ashr.clone.saas_control_plane.v1"
API_KEY_ADMIN_SCOPE = "api_key:write"
API_KEY_READ_SCOPE = "api_key:read"
API_KEY_LEGACY_ADMIN_SCOPE = "key:admin"
API_KEY_LEGACY_READ_SCOPE = "key:read"
RUN_CREATE_SCOPE = "run:create"
RUN_UPLOAD_SCOPE = "run:upload"
TRACE_INGEST_SCOPE = "trace:ingest"
USAGE_READ_SCOPE = "usage:read"
AUDIT_READ_SCOPE = "audit:read"
ADMIN_ALL_SCOPE = "admin:all"
CONTROL_PLANE_SCOPES = {
    "project:read",
    "project:write",
    "dataset:read",
    "dataset:write",
    "run:read",
    RUN_CREATE_SCOPE,
    RUN_UPLOAD_SCOPE,
    TRACE_INGEST_SCOPE,
    "artifact:upload",
    "evidence:read",
    "release_gate:evaluate",
    API_KEY_READ_SCOPE,
    API_KEY_ADMIN_SCOPE,
    USAGE_READ_SCOPE,
    AUDIT_READ_SCOPE,
    ADMIN_ALL_SCOPE,
}
API_KEY_SCOPE_ALIASES = {
    API_KEY_LEGACY_ADMIN_SCOPE: {API_KEY_ADMIN_SCOPE, API_KEY_READ_SCOPE},
    API_KEY_LEGACY_READ_SCOPE: {API_KEY_READ_SCOPE},
    "sdk:submit": {RUN_CREATE_SCOPE},
    "runs:write": {RUN_CREATE_SCOPE, RUN_UPLOAD_SCOPE, "sdk:submit"},
    "write:runs": {RUN_CREATE_SCOPE, RUN_UPLOAD_SCOPE, "sdk:submit"},
    "traces:write": {TRACE_INGEST_SCOPE},
    API_KEY_ADMIN_SCOPE: {API_KEY_READ_SCOPE},
    ADMIN_ALL_SCOPE: set(CONTROL_PLANE_SCOPES),
}
SAAS_QUOTA_LIMITS = {
    "api_key.create": 100,
    "run.upload": 10_000,
    "sdk.submit": 10_000,
    "trace.ingest": 100_000,
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass(slots=True)
class SaaSControlPlaneStore:
    api_keys: dict[str, JsonDict] = field(default_factory=dict)
    api_key_rate_limits: dict[str, JsonDict] = field(default_factory=dict)
    uploads: dict[str, JsonDict] = field(default_factory=dict)
    trace_batches: dict[str, JsonDict] = field(default_factory=dict)
    sdk_submissions: dict[str, JsonDict] = field(default_factory=dict)
    audit_log: dict[str, JsonDict] = field(default_factory=dict)
    usage_ledger: dict[str, JsonDict] = field(default_factory=dict)
    idempotency_keys: dict[str, JsonDict] = field(default_factory=dict)


class SaaSControlPlaneService:
    """Local enterprise SaaS control-plane wrapper around CloudApiService.

    This layer models buyer-facing Ashr++ SaaS surfaces without calling hosted
    billing or mutating Ashr APIs: API key governance, SDK submit, run upload,
    trace ingestion, quota ledger integration, and tenant/project/run lifecycle.
    """

    def __init__(
        self,
        cloud: CloudApiService | None = None,
        *,
        store: SaaSControlPlaneStore | None = None,
        release_gate_evaluator: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        self.cloud = cloud or CloudApiService()
        self.store = store or SaaSControlPlaneStore()
        self.release_gate_client = LocalReleaseGateBridgeClient(release_gate_evaluator or _deterministic_release_gate_evaluator)

    def register_release_gate_evaluator(self, evaluator: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> None:
        self.release_gate_client = LocalReleaseGateBridgeClient(evaluator)

    def bootstrap_project(self, *, tenant_name: str, project_name: str, tenant_id: str | None = None, project_id: str | None = None) -> JsonDict:
        tenant = self.cloud.create_tenant(tenant_name, tenant_id=tenant_id)
        project = self.cloud.create_project(tenant["tenant_id"], project_name, project_id=project_id)
        self.cloud.quota.configure(tenant["tenant_id"], project["project_id"], SAAS_QUOTA_LIMITS)
        return {"schema_version": CONTROL_PLANE_SCHEMA_VERSION, "tenant": tenant, "project": project, "quota": self.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])}

    def create_api_key(
        self,
        tenant_id: str,
        project_id: str,
        *,
        name: str,
        scopes: list[str],
        key_id: str | None = None,
        auth_key_id: str | None = None,
        reveal_secret: bool = False,
    ) -> JsonDict:
        project = self.cloud.get_project(tenant_id, project_id)
        if auth_key_id is not None:
            self.authenticate_api_key(project["tenant_id"], project["project_id"], key_id=auth_key_id, scope=API_KEY_ADMIN_SCOPE)
        normalized_scopes = [_normalize_scope(scope) for scope in scopes]
        if not normalized_scopes:
            raise ValidationError("api key scopes must not be empty")
        self.cloud.quota.consume(project["tenant_id"], project["project_id"], "api_key.create")
        key_id = key_id or _new_id("key")
        if key_id in self.store.api_keys:
            raise ValidationError(f"api key already exists: {key_id}")
        synthetic_secret = f"ashr_local_{key_id}_{uuid4().hex}"
        digest = _secret_hash(synthetic_secret)
        now = _utc_now()
        record = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "tenant_id": project["tenant_id"],
            "project_id": project["project_id"],
            "key_id": key_id,
            "name": str(name),
            "prefix": "ashr_local_***",
            "secret_hash_sha256": digest,
            "secret_value_present": False,
            "one_time_secret_displayed": bool(reveal_secret),
            "verify_mode": "sha256",
            "status": "active",
            "scopes": normalized_scopes,
            "created_at": now,
            "revoked_at": None,
            "last_used_at": None,
        }
        self.store.api_keys[key_id] = record
        public = _public_api_key(record)
        self._append_audit(project["tenant_id"], project["project_id"], "api_key.create", target_id=key_id, api_key_id=auth_key_id, after=public)
        if reveal_secret:
            return {**public, "one_time_secret": synthetic_secret, "one_time_secret_displayed": True, "secret_value_present": True}
        return public

    def revoke_api_key(self, tenant_id: str, project_id: str, key_id: str, *, auth_key_id: str | None = None) -> JsonDict:
        if auth_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=auth_key_id, scope=API_KEY_ADMIN_SCOPE)
        record = self._api_key_record(tenant_id, project_id, key_id)
        before = _public_api_key(record)
        record["status"] = "revoked"
        record["revoked_at"] = _utc_now()
        public = _public_api_key(record)
        self._append_audit(tenant_id, project_id, "api_key.revoke", target_id=key_id, api_key_id=auth_key_id, before=before, after=public)
        return public

    def list_api_keys(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None) -> list[JsonDict]:
        self.cloud.get_project(tenant_id, project_id)
        if auth_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=auth_key_id, scope=API_KEY_READ_SCOPE)
        return [_public_api_key(record) for record in self.store.api_keys.values() if record.get("tenant_id") == str(tenant_id) and record.get("project_id") == str(project_id)]

    def authenticate_api_key(self, tenant_id: str, project_id: str, *, key_id: str, scope: str) -> JsonDict:
        """Authenticate a local API key by id and required scope.

        This sandbox contract intentionally never accepts or returns a raw secret;
        the caller supplies the key id and desired scope, and receives a public,
        redacted key view when the key is active and authorized.
        """
        record = self._api_key_record(tenant_id, project_id, key_id)
        required_scope = _normalize_scope(scope)
        if record.get("status") != "active":
            raise ValidationError(f"api key is not active: {key_id}")
        if not _scope_allows(record.get("scopes", []), required_scope):
            raise ValidationError(f"api key {key_id} missing required scope: {required_scope}")
        self._consume_api_key_rate(record, required_scope)
        record["last_used_at"] = _utc_now()
        return {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "tenant_id": record.get("tenant_id"),
            "project_id": record.get("project_id"),
            "key_id": record.get("key_id"),
            "authenticated": True,
            "required_scope": required_scope,
            "api_key": _public_api_key(record),
            "secret_value_present": False,
        }


    def verify_api_key_secret(self, tenant_id: str, project_id: str, *, key_id: str, secret: str, scope: str | None = None) -> JsonDict:
        record = self._api_key_record(tenant_id, project_id, key_id)
        if record.get("status") != "active":
            raise ValidationError(f"api key is not active: {key_id}")
        if _secret_hash(secret) != record.get("secret_hash_sha256"):
            raise ValidationError("api key secret verification failed")
        if scope is not None:
            return self.authenticate_api_key(tenant_id, project_id, key_id=key_id, scope=scope)
        record["last_used_at"] = _utc_now()
        return {"schema_version": CONTROL_PLANE_SCHEMA_VERSION, "tenant_id": tenant_id, "project_id": project_id, "key_id": key_id, "verified": True, "api_key": _public_api_key(record), "secret_value_present": False}

    def configure_api_key_rate_limit(self, tenant_id: str, project_id: str, *, key_id: str, operation: str, limit: int, period: str = "local-window", auth_key_id: str | None = None) -> JsonDict:
        if auth_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=auth_key_id, scope=API_KEY_ADMIN_SCOPE)
        record = self._api_key_record(tenant_id, project_id, key_id)
        if limit <= 0:
            raise ValidationError("api key rate limit must be positive")
        bucket_key = _api_key_rate_key(tenant_id, project_id, key_id, operation, period)
        bucket = {"schema_version": CONTROL_PLANE_SCHEMA_VERSION, "tenant_id": tenant_id, "project_id": project_id, "key_id": key_id, "operation": operation, "period": period, "limit": int(limit), "used": 0, "remaining": int(limit), "created_at": _utc_now()}
        self.store.api_key_rate_limits[bucket_key] = bucket
        public = _public_api_key(record)
        self._append_audit(tenant_id, project_id, "api_key.rate_limit.configure", target_id=key_id, api_key_id=auth_key_id, after={"api_key": public, "rate_limit": bucket})
        return _jsonable(bucket)

    def api_key_rate_limit_snapshot(self, tenant_id: str, project_id: str, *, key_id: str | None = None) -> JsonDict:
        buckets = [bucket for bucket in self.store.api_key_rate_limits.values() if bucket.get("tenant_id") == str(tenant_id) and bucket.get("project_id") == str(project_id) and (key_id is None or bucket.get("key_id") == str(key_id))]
        return {"schema_version": CONTROL_PLANE_SCHEMA_VERSION, "tenant_id": tenant_id, "project_id": project_id, "key_id": key_id, "rate_limits": _jsonable(buckets)}

    def sdk_submit_run(self, tenant_id: str, project_id: str, *, dataset_id: str, agent_ref: str, run_id: str | None = None, metadata: Mapping[str, Any] | None = None, api_key_id: str | None = None, idempotency_key: str | None = None, request_id: str | None = None) -> JsonDict:
        if api_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=api_key_id, scope="sdk:submit")
        idem = self._idempotency_lookup(tenant_id, project_id, "sdk.submit", idempotency_key)
        if idem is not None:
            return idem
        self.cloud.quota.check(tenant_id, project_id, "sdk.submit")
        run = self.cloud.create_queued_run(tenant_id, project_id, dataset_id=dataset_id, run_id=run_id, runner_id="sdk-submit", metadata={"submitted_by": "sdk", "agent_ref": agent_ref, **dict(metadata or {})})
        self._consume_usage(tenant_id, project_id, "sdk.submit", api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id, run_id=run["run_id"])
        submission = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "submission_id": _new_id("sdksub"),
            "tenant_id": tenant_id,
            "project_id": project_id,
            "dataset_id": dataset_id,
            "run_id": run["run_id"],
            "agent_ref": str(agent_ref),
            "status": "accepted",
            "idempotency_key": idempotency_key,
            "request_id": request_id,
            "created_at": _utc_now(),
        }
        self.store.sdk_submissions[submission["submission_id"]] = submission
        response = _jsonable({"submission": submission, "run": run})
        self._idempotency_store(tenant_id, project_id, "sdk.submit", idempotency_key, response)
        self._append_audit(tenant_id, project_id, "sdk.submit", target_id=run["run_id"], api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id, after={"run_id": run["run_id"], "submission_id": submission["submission_id"]})
        return response

    def upload_run_result(self, tenant_id: str, project_id: str, run_id: str, result: Mapping[str, Any], *, upload_id: str | None = None, api_key_id: str | None = None, idempotency_key: str | None = None, request_id: str | None = None) -> JsonDict:
        if api_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=api_key_id, scope=RUN_UPLOAD_SCOPE)
        idem = self._idempotency_lookup(tenant_id, project_id, "run.upload", idempotency_key)
        if idem is not None:
            return idem
        run = self.cloud.get_run(tenant_id, project_id, run_id)
        self._consume_usage(tenant_id, project_id, "run.upload", api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id)
        upload_id = upload_id or _new_id("upload")
        payload = _jsonable(dict(result))
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        record = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "upload_id": upload_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run["run_id"],
            "payload_sha256": digest,
            "payload_keys": sorted(payload.keys()),
            "raw_payload_included": False,
            "idempotency_key": idempotency_key,
            "request_id": request_id,
            "status": "uploaded",
            "created_at": _utc_now(),
        }
        self.store.uploads[upload_id] = record
        response = _jsonable(record)
        self._idempotency_store(tenant_id, project_id, "run.upload", idempotency_key, response)
        self._append_audit(tenant_id, project_id, "run.upload", target_id=run_id, api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id, after={"upload_id": upload_id, "payload_sha256": digest})
        return response

    def ingest_trace(self, tenant_id: str, project_id: str, run_id: str, observations: list[Mapping[str, Any]], *, batch_id: str | None = None, api_key_id: str | None = None, idempotency_key: str | None = None, request_id: str | None = None) -> JsonDict:
        if api_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=api_key_id, scope=TRACE_INGEST_SCOPE)
        idem = self._idempotency_lookup(tenant_id, project_id, "trace.ingest", idempotency_key)
        if idem is not None:
            return idem
        self.cloud.get_run(tenant_id, project_id, run_id)
        if not observations:
            raise ValidationError("trace ingestion requires at least one observation")
        self._consume_usage(tenant_id, project_id, "trace.ingest", units=len(observations), api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id)
        normalized_observations = [_jsonable(observation) for observation in observations]
        batch_sha256 = hashlib.sha256(json.dumps(normalized_observations, sort_keys=True).encode("utf-8")).hexdigest()
        appended = [self.cloud.append_observation(tenant_id, project_id, run_id, observation) for observation in normalized_observations]
        batch_id = batch_id or _new_id("tracebatch")
        record = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "batch_id": batch_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run_id,
            "observation_count": len(appended),
            "observation_ids": [item.get("observation_id") for item in appended],
            "batch_sha256": batch_sha256,
            "raw_payload_included": False,
            "idempotency_key": idempotency_key,
            "request_id": request_id,
            "status": "ingested",
            "created_at": _utc_now(),
        }
        self.store.trace_batches[batch_id] = record
        response = _jsonable(record)
        self._idempotency_store(tenant_id, project_id, "trace.ingest", idempotency_key, response)
        self._append_audit(tenant_id, project_id, "trace.ingest", target_id=run_id, api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id, after={"batch_id": batch_id, "batch_sha256": batch_sha256})
        return response

    def lifecycle_snapshot(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        tenant = self.cloud.get_tenant(tenant_id)
        project = self.cloud.get_project(tenant_id, project_id)
        run = self.cloud.get_run(tenant_id, project_id, run_id)
        return {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "tenant_id": tenant["tenant_id"],
            "project_id": project["project_id"],
            "run_id": run["run_id"],
            "tenant_status": "active",
            "project_status": "active",
            "run_status": run["status"],
            "run_result_status": run.get("result_status"),
            "status_history": run.get("status_history", []),
            "quota": self.cloud.quota_snapshot(tenant_id, project_id),
            "api_keys": self.list_api_keys(tenant_id, project_id),
            "uploads": [item for item in self.store.uploads.values() if item.get("run_id") == run_id],
            "trace_batches": [item for item in self.store.trace_batches.values() if item.get("run_id") == run_id],
            "usage_ledger": [item for item in self.store.usage_ledger.values() if item.get("tenant_id") == tenant_id and item.get("project_id") == project_id and item.get("run_id") in {None, run_id}],
            "audit_log": [item for item in self.store.audit_log.values() if item.get("tenant_id") == tenant_id and item.get("project_id") == project_id and item.get("target_id") in {None, run_id}],
        }

    def usage_snapshot(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None) -> JsonDict:
        self.cloud.get_project(tenant_id, project_id)
        if auth_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=auth_key_id, scope=USAGE_READ_SCOPE)
        events = [item for item in self.store.usage_ledger.values() if item.get("tenant_id") == str(tenant_id) and item.get("project_id") == str(project_id)]
        totals: dict[str, int] = {}
        for event in events:
            operation = str(event.get("operation"))
            totals[operation] = totals.get(operation, 0) + int(event.get("units", 0))
        return {"schema_version": CONTROL_PLANE_SCHEMA_VERSION, "tenant_id": tenant_id, "project_id": project_id, "events": _jsonable(events), "totals": totals, "quota": self.cloud.quota_snapshot(tenant_id, project_id)}

    def audit_snapshot(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None, action: str | None = None, target_id: str | None = None, api_key_id: str | None = None, limit: int | None = None) -> JsonDict:
        self.cloud.get_project(tenant_id, project_id)
        if auth_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=auth_key_id, scope=AUDIT_READ_SCOPE)
        ledger_events = [item for item in self.store.audit_log.values() if item.get("tenant_id") == str(tenant_id) and item.get("project_id") == str(project_id)]
        chain = verify_audit_chain(ledger_events)
        events = ledger_events
        if action is not None:
            events = [item for item in events if item.get("action") == str(action)]
        if target_id is not None:
            events = [item for item in events if item.get("target_id") == str(target_id)]
        if api_key_id is not None:
            events = [item for item in events if item.get("api_key_id") == str(api_key_id)]
        events = _audit_events_in_chain_order(events)
        if limit is not None:
            if limit <= 0:
                raise ValidationError("audit log limit must be positive")
            events = events[-int(limit) :]
        return {"schema_version": CONTROL_PLANE_SCHEMA_VERSION, "tenant_id": tenant_id, "project_id": project_id, "filters": {"action": action, "target_id": target_id, "api_key_id": api_key_id, "limit": limit}, "events": _jsonable(events), "chain": chain}

    def evaluate_release_gate(self, tenant_id: str, project_id: str, run_id: str, *, policy: Mapping[str, Any] | None = None, auth_key_id: str | None = None, request_id: str | None = None, idempotency_key: str | None = None, timeout_seconds: float = 5.0) -> JsonDict:
        if auth_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=auth_key_id, scope="release_gate:evaluate")
        lifecycle = self.lifecycle_snapshot(tenant_id, project_id, run_id)
        result = evaluate_lifecycle_with_release_gate(
            self.release_gate_client,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            lifecycle=lifecycle,
            policy=policy,
            request_id=request_id,
            idempotency_key=idempotency_key,
            timeout_seconds=timeout_seconds,
        )
        grade = result.get("grade_result") if isinstance(result.get("grade_result"), Mapping) else {}
        self._append_audit(
            tenant_id,
            project_id,
            "release_gate.evaluate",
            target_id=run_id,
            api_key_id=auth_key_id,
            idempotency_key=str(result.get("idempotency_key")) if result.get("idempotency_key") is not None else idempotency_key,
            request_id=str(result.get("request_id")) if result.get("request_id") is not None else request_id,
            after={"passed": grade.get("passed"), "score": grade.get("score"), "label": grade.get("label"), "transport": result.get("transport")},
        )
        return _jsonable({**result, "schema_version": CONTROL_PLANE_SCHEMA_VERSION, "local_only": True, "ashr_api_used": False})

    def verify_audit_chain_snapshot(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None, action: str | None = None, target_id: str | None = None, api_key_id: str | None = None, limit: int | None = None) -> JsonDict:
        audit = self.audit_snapshot(tenant_id, project_id, auth_key_id=auth_key_id, action=action, target_id=target_id, api_key_id=api_key_id, limit=limit)
        return {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "filters": audit.get("filters", {}),
            "verification": audit.get("chain", {}),
            "event_count": len(audit.get("events", [])) if isinstance(audit.get("events"), list) else 0,
            "local_only": True,
            "ashr_api_used": False,
        }

    def verify_release_evidence_packet(self, tenant_id: str, project_id: str, packet: Mapping[str, Any], *, run_id: str | None = None, auth_key_id: str | None = None) -> JsonDict:
        self.cloud.get_project(tenant_id, project_id)
        if auth_key_id is not None:
            self.authenticate_api_key(tenant_id, project_id, key_id=auth_key_id, scope="evidence:read")
        verification = _verify_release_evidence_packet(packet)
        failures = list(verification.get("failures", [])) if isinstance(verification.get("failures"), list) else []
        if str(packet.get("tenant_id") or "") != str(tenant_id):
            failures.append({"reason": "tenant_id_mismatch", "expected": str(tenant_id), "actual": packet.get("tenant_id")})
        if str(packet.get("project_id") or "") != str(project_id):
            failures.append({"reason": "project_id_mismatch", "expected": str(project_id), "actual": packet.get("project_id")})
        if run_id is not None and str(packet.get("run_id") or "") != str(run_id):
            failures.append({"reason": "run_id_mismatch", "expected": str(run_id), "actual": packet.get("run_id")})
        return _jsonable(
            {
                **verification,
                "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
                "verification_schema_version": verification.get("schema_version"),
                "verified": not failures,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id or packet.get("run_id"),
                "failures": failures,
                "local_only": True,
                "ashr_api_used": False,
            }
        )


    def _consume_usage(self, tenant_id: str, project_id: str, operation: str, *, units: int = 1, api_key_id: str | None = None, idempotency_key: str | None = None, request_id: str | None = None, run_id: str | None = None) -> JsonDict:
        self.cloud.quota.consume(tenant_id, project_id, operation, units=units)
        usage_event_id = _new_id("usage")
        record = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "usage_event_id": usage_event_id,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "run_id": run_id,
            "api_key_id": api_key_id,
            "operation": str(operation),
            "units": int(units),
            "source": "local_control_plane",
            "idempotency_key": idempotency_key,
            "request_id": request_id,
            "created_at": _utc_now(),
        }
        self.store.usage_ledger[usage_event_id] = record
        return _jsonable(record)

    def _append_audit(self, tenant_id: str, project_id: str, action: str, *, target_id: str | None = None, api_key_id: str | None = None, idempotency_key: str | None = None, request_id: str | None = None, before: Mapping[str, Any] | None = None, after: Mapping[str, Any] | None = None) -> JsonDict:
        event_id = _new_id("audit")
        before_payload = _jsonable(before or {})
        after_payload = _jsonable(after or {})
        previous_event = _audit_chain_tail(self.store.audit_log.values(), str(tenant_id), str(project_id))
        record = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "audit_event_id": event_id,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "chain_position": int(previous_event.get("chain_position", -1)) + 1 if previous_event else 0,
            "previous_audit_event_id": previous_event.get("audit_event_id") if previous_event else None,
            "previous_audit_event_sha256": previous_event.get("audit_event_sha256") if previous_event else None,
            "api_key_id": api_key_id,
            "action": str(action),
            "target_id": target_id,
            "before_sha256": hashlib.sha256(json.dumps(before_payload, sort_keys=True).encode("utf-8")).hexdigest() if before_payload else None,
            "after_sha256": hashlib.sha256(json.dumps(after_payload, sort_keys=True).encode("utf-8")).hexdigest() if after_payload else None,
            "idempotency_key": idempotency_key,
            "request_id": request_id,
            "created_at": _utc_now(),
        }
        record["audit_event_sha256"] = _audit_event_hash(record)
        self.store.audit_log[event_id] = record
        return _jsonable(record)

    def _consume_api_key_rate(self, record: Mapping[str, Any], operation: str) -> None:
        key_id = str(record.get("key_id"))
        tenant_id = str(record.get("tenant_id"))
        project_id = str(record.get("project_id"))
        candidates = [bucket for bucket in self.store.api_key_rate_limits.values() if bucket.get("tenant_id") == tenant_id and bucket.get("project_id") == project_id and bucket.get("key_id") == key_id and bucket.get("operation") in {operation, "*"}]
        for bucket in candidates:
            used = int(bucket.get("used") or 0)
            limit = int(bucket.get("limit") or 0)
            if used + 1 > limit:
                raise ValidationError(f"api key rate limit exceeded for {key_id}: {operation}")
        for bucket in candidates:
            bucket["used"] = int(bucket.get("used") or 0) + 1
            bucket["remaining"] = max(0, int(bucket.get("limit") or 0) - int(bucket.get("used") or 0))
            bucket["last_used_at"] = _utc_now()

    def _idempotency_lookup(self, tenant_id: str, project_id: str, operation: str, idempotency_key: str | None) -> JsonDict | None:
        if not idempotency_key:
            return None
        key = _idempotency_record_key(tenant_id, project_id, operation, idempotency_key)
        record = self.store.idempotency_keys.get(key)
        if record is None:
            return None
        response = _jsonable(record.get("response", {}))
        if isinstance(response, dict):
            response.setdefault("idempotent_replay", True)
        return response

    def _idempotency_store(self, tenant_id: str, project_id: str, operation: str, idempotency_key: str | None, response: Mapping[str, Any]) -> None:
        if not idempotency_key:
            return
        key = _idempotency_record_key(tenant_id, project_id, operation, idempotency_key)
        self.store.idempotency_keys[key] = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "operation": str(operation),
            "idempotency_key": str(idempotency_key),
            "response": _jsonable(response),
            "created_at": _utc_now(),
        }

    def _api_key_record(self, tenant_id: str, project_id: str, key_id: str) -> JsonDict:
        record = self.store.api_keys.get(str(key_id))
        if not record or record.get("tenant_id") != str(tenant_id) or record.get("project_id") != str(project_id):
            raise NotFoundError("api key not found for project")
        return record


def _normalize_scope(scope: str) -> str:
    parsed = str(scope).strip()
    if not parsed:
        raise ValidationError("required scope must not be empty")
    return parsed


def _scope_allows(granted_scopes: Any, required_scope: str) -> bool:
    granted = {str(scope).strip() for scope in granted_scopes or [] if str(scope).strip()}
    expanded = set(granted)
    for scope in list(granted):
        expanded.update(API_KEY_SCOPE_ALIASES.get(scope, set()))
    if "*" in expanded or ADMIN_ALL_SCOPE in expanded or required_scope in expanded:
        return True
    for scope in expanded:
        if scope.endswith(":*") and required_scope.startswith(f"{scope[:-2]}:"):
            return True
    return False


def _secret_hash(secret: str) -> str:
    return hashlib.sha256(str(secret).encode("utf-8")).hexdigest()


def _api_key_rate_key(tenant_id: str, project_id: str, key_id: str, operation: str, period: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{project_id}:{key_id}:{operation}:{period}".encode("utf-8")).hexdigest()


def _idempotency_record_key(tenant_id: str, project_id: str, operation: str, idempotency_key: str) -> str:
    raw = f"{tenant_id}:{project_id}:{operation}:{idempotency_key}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _audit_event_hash(event: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in _jsonable(dict(event)).items() if key != "audit_event_sha256"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _audit_events_in_chain_order(events: Iterable[Mapping[str, Any]]) -> list[JsonDict]:
    normalized = [_jsonable(dict(event)) for event in events]
    return sorted(normalized, key=lambda item: (int(item.get("chain_position", 0) or 0), str(item.get("created_at") or ""), str(item.get("audit_event_id") or "")))


def _audit_chain_tail(events: Iterable[Mapping[str, Any]], tenant_id: str, project_id: str) -> JsonDict | None:
    scoped = [event for event in events if event.get("tenant_id") == tenant_id and event.get("project_id") == project_id]
    ordered = _audit_events_in_chain_order(scoped)
    return ordered[-1] if ordered else None


def verify_audit_chain(events: Iterable[Mapping[str, Any]]) -> JsonDict:
    ordered = _audit_events_in_chain_order(events)
    previous_hash: str | None = None
    previous_id: str | None = None
    failures: list[JsonDict] = []
    for index, event in enumerate(ordered):
        event_id = str(event.get("audit_event_id") or "")
        expected_hash = _audit_event_hash(event)
        if event.get("audit_event_sha256") != expected_hash:
            failures.append({"audit_event_id": event_id, "reason": "event_hash_mismatch"})
        if event.get("previous_audit_event_id") != previous_id:
            failures.append({"audit_event_id": event_id, "reason": "previous_event_id_mismatch"})
        if event.get("previous_audit_event_sha256") != previous_hash:
            failures.append({"audit_event_id": event_id, "reason": "previous_event_hash_mismatch"})
        chain_position_raw = event.get("chain_position")
        chain_position = int(chain_position_raw) if chain_position_raw is not None else -1
        if chain_position != index:
            failures.append({"audit_event_id": event_id, "reason": "chain_position_mismatch"})
        previous_hash = str(event.get("audit_event_sha256") or expected_hash)
        previous_id = event_id
    return {
        "verified": not failures,
        "event_count": len(ordered),
        "head_audit_event_id": ordered[0].get("audit_event_id") if ordered else None,
        "head_audit_event_sha256": ordered[0].get("audit_event_sha256") if ordered else None,
        "tail_audit_event_id": ordered[-1].get("audit_event_id") if ordered else None,
        "tail_audit_event_sha256": ordered[-1].get("audit_event_sha256") if ordered else None,
        "failures": failures,
    }


def _public_api_key(record: Mapping[str, Any]) -> JsonDict:
    return {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "tenant_id": record.get("tenant_id"),
        "project_id": record.get("project_id"),
        "key_id": record.get("key_id"),
        "name": record.get("name"),
        "prefix": record.get("prefix"),
        "secret_hash_present": bool(record.get("secret_hash_sha256")),
        "secret_value_present": False,
        "status": record.get("status"),
        "scopes": list(record.get("scopes", [])),
        "created_at": record.get("created_at"),
        "revoked_at": record.get("revoked_at"),
        "last_used_at": record.get("last_used_at"),
        "one_time_secret_displayed": bool(record.get("one_time_secret_displayed", False)),
        "verify_mode": record.get("verify_mode"),
    }


def _deterministic_release_gate_evaluator(payload: Mapping[str, Any]) -> JsonDict:
    lifecycle = payload.get("inputs") if isinstance(payload.get("inputs"), Mapping) else {}
    policy = payload.get("policy") if isinstance(payload.get("policy"), Mapping) else {}
    minimum_uploads = int(policy.get("minimum_uploads", 1) if policy.get("minimum_uploads") is not None else 1)
    minimum_trace_batches = int(policy.get("minimum_trace_batches", 1) if policy.get("minimum_trace_batches") is not None else 1)
    run_status = str(lifecycle.get("run_status") or "")
    upload_count = int(lifecycle.get("upload_count") or 0)
    trace_batch_count = int(lifecycle.get("trace_batch_count") or 0)
    passed = run_status in {"queued", "running", "completed", "succeeded", "accepted"} and upload_count >= minimum_uploads and trace_batch_count >= minimum_trace_batches
    score = 1.0 if passed else 0.0
    return {
        "scenario_id": str(payload.get("run_id") or lifecycle.get("run_id") or "local_release_gate"),
        "passed": passed,
        "score": score,
        "label": "release_gate_pass" if passed else "release_gate_hold",
        "reason": "Local deterministic release gate accepted lifecycle evidence" if passed else "Local deterministic release gate requires uploaded run evidence",
        "expected": {"minimum_uploads": minimum_uploads, "minimum_trace_batches": minimum_trace_batches},
        "actual": {"run_status": run_status, "upload_count": upload_count, "trace_batch_count": trace_batch_count},
        "metrics": {"target_contract": payload.get("target_contract"), "evaluator": "local_deterministic_stub"},
    }


CONTROL_PLANE_OPENAPI_VERSION = "3.0.3"


def control_plane_openapi_document() -> JsonDict:
    """Return the public local control-plane HTTP contract.

    The schema is intentionally hand-written and conservative so it can be
    served without importing a web framework or introspecting environment
    variables. It documents request fields, not generated secrets or stored
    secret hashes.
    """

    tenant_project_body = {
        "type": "object",
        "properties": {
            "tenant_id": {"type": "string"},
            "organization_id": {"type": "string"},
            "tenant": {"type": "string"},
            "auth_key_id": {"type": "string"},
            "api_key_id": {"type": "string"},
        },
    }
    json_response = {
        "description": "JSON response",
        "content": {"application/json": {"schema": {"type": "object"}}},
    }
    json_request = {
        "required": False,
        "content": {"application/json": {"schema": {"type": "object"}}},
    }
    return {
        "openapi": CONTROL_PLANE_OPENAPI_VERSION,
        "info": {
            "title": "Ashr SaaS Control Plane Runtime",
            "version": CONTROL_PLANE_SCHEMA_VERSION,
            "description": "Local hosted/self-host control-plane HTTP adapter for SaaSControlPlaneRouter.",
        },
        "paths": {
            "/healthz": {
                "get": {
                    "summary": "Runtime health check",
                    "responses": {"200": json_response},
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "OpenAPI document",
                    "responses": {"200": json_response},
                }
            },
            "/v1/bootstrap": {
                "post": {
                    "summary": "Bootstrap tenant/project quota state",
                    "requestBody": json_request,
                    "responses": {"201": json_response, "400": json_response},
                }
            },
            "/v1/projects/{project_id}/api-keys": {
                "get": {
                    "summary": "List redacted API keys",
                    "parameters": [{"name": "project_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {**json_request, "content": {"application/json": {"schema": tenant_project_body}}},
                    "responses": {"200": json_response, "400": json_response, "404": json_response},
                },
                "post": {
                    "summary": "Create an API key record; optional reveal_secret returns one synthetic local secret once",
                    "requestBody": json_request,
                    "responses": {"201": json_response, "400": json_response, "404": json_response},
                },
            },
            "/v1/projects/{project_id}/api-keys/{key_id}/revoke": {
                "post": {"summary": "Revoke an API key", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/api-keys/{key_id}/authenticate": {
                "post": {"summary": "Validate a key id and scope", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/api-keys/{key_id}/verify": {
                "post": {"summary": "Verify a one-time local API key secret against its stored hash", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/api-keys/{key_id}/rate-limit": {
                "post": {"summary": "Configure a per-key operation rate-limit bucket", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/api-keys/rate-limits": {
                "get": {"summary": "List per-key operation rate-limit buckets", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/audit-log": {
                "get": {"summary": "Query public-safe audit events for API-key, rate-limit, ingestion, and release-gate actions", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/audit-chain/verify": {
                "post": {"summary": "Verify the public-safe audit event hash chain", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/runs/{run_id}/release-evidence": {
                "get": {"summary": "Build a public-safe release evidence packet", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/runs/{run_id}/release-evidence/verify": {
                "post": {"summary": "Verify a submitted or current release evidence packet without raw payloads or secrets", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/sdk-submit": {
                "post": {"summary": "Submit a run through the SDK control-plane surface", "requestBody": json_request, "responses": {"202": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/runs/{run_id}/upload": {
                "post": {"summary": "Upload redacted run result metadata", "requestBody": json_request, "responses": {"202": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/runs/{run_id}/trace-events": {
                "post": {"summary": "Ingest trace event metadata", "requestBody": json_request, "responses": {"202": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/runs/{run_id}/lifecycle": {
                "get": {"summary": "Fetch project/run lifecycle snapshot", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
            "/v1/projects/{project_id}/runs/{run_id}/release-gate": {
                "post": {"summary": "Evaluate the local release gate from the lifecycle snapshot", "requestBody": json_request, "responses": {"200": json_response, "400": json_response, "404": json_response}}
            },
        },
    }


def _control_plane_error_response(status_code: int, code: str, message: str) -> JsonDict:
    return {
        "status_code": status_code,
        "body": {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "error": {"code": code, "message": message},
        },
    }


def _json_response_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _query_body(environ: Mapping[str, Any]) -> JsonDict:
    parsed = parse_qs(str(environ.get("QUERY_STRING") or ""), keep_blank_values=True)
    body: JsonDict = {}
    for key, values in parsed.items():
        if not values:
            continue
        if len(values) == 1:
            body[str(key)] = values[0]
        else:
            body[str(key)] = list(values)
    return body


def _read_json_wsgi_body(environ: Mapping[str, Any]) -> JsonDict:
    try:
        length = int(str(environ.get("CONTENT_LENGTH") or "0") or "0")
    except ValueError as exc:
        raise ValidationError("CONTENT_LENGTH must be an integer") from exc
    if length < 0:
        raise ValidationError("CONTENT_LENGTH must be non-negative")
    if length == 0:
        return {}
    stream = environ.get("wsgi.input")
    if stream is None or not hasattr(stream, "read"):
        raise ValidationError("wsgi.input is required")
    raw = stream.read(length)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("request body must be valid UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValidationError("request JSON body must be an object")
    return dict(payload)


class SaaSControlPlaneWSGIApp:
    """Framework-free WSGI adapter for :class:`SaaSControlPlaneRouter`.

    The adapter is suitable for local hosted/self-host smoke deployments via
    ``wsgiref.simple_server`` and for in-process tests. It never reads process
    secrets or API-key environment variables; authentication test fixtures pass
    explicit key ids through JSON payloads, matching the in-process router.
    """

    server_software = "ashr-saas-control-plane-wsgi/1"

    def __init__(self, router: SaaSControlPlaneRouter | None = None, *, service: SaaSControlPlaneService | None = None) -> None:
        if router is not None and service is not None:
            raise ValidationError("provide router or service, not both")
        self.router = router or SaaSControlPlaneRouter(service)

    def __call__(self, environ: Mapping[str, Any], start_response: Callable[[str, list[tuple[str, str]]], Any]) -> Iterable[bytes]:
        response = self.handle_environ(environ)
        status_code = int(response["status_code"])
        body_bytes = _json_response_bytes(response["body"])
        status = f"{status_code} {_http_status_reason(status_code)}"
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body_bytes))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ]
        start_response(status, headers)
        return [body_bytes]

    def handle_environ(self, environ: Mapping[str, Any]) -> JsonDict:
        method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        path = str(environ.get("PATH_INFO") or "/")

        if path == "/healthz" and method == "GET":
            return {
                "status_code": 200,
                "body": {
                    "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
                    "status": "ok",
                    "service": "ashr-saas-control-plane",
                    "local_only": True,
                    "ashr_api_used": False,
                },
            }
        if path == "/openapi.json" and method == "GET":
            return {"status_code": 200, "body": control_plane_openapi_document()}

        try:
            body = _query_body(environ)
            body.update(_read_json_wsgi_body(environ))
        except Exception as exc:
            code = getattr(exc, "code", "validation_error")
            return _control_plane_error_response(400, str(code), str(exc))
        return self.router.handle(method, path, body)


def create_control_plane_wsgi_app(service: SaaSControlPlaneService | None = None, router: SaaSControlPlaneRouter | None = None) -> SaaSControlPlaneWSGIApp:
    return SaaSControlPlaneWSGIApp(router, service=service)


def serve_control_plane_http(host: str = "127.0.0.1", port: int = 8080, *, service: SaaSControlPlaneService | None = None, router: SaaSControlPlaneRouter | None = None):
    """Create a stdlib WSGI HTTP server for the SaaS control plane.

    The returned ``wsgiref.simple_server.WSGIServer`` is not started
    automatically; callers can invoke ``serve_forever()`` or coordinate it in a
    test thread.
    """

    from wsgiref.simple_server import make_server

    app = create_control_plane_wsgi_app(service=service, router=router)
    return make_server(host, int(port), app)


def _http_status_reason(status_code: int) -> str:
    return {
        200: "OK",
        201: "Created",
        202: "Accepted",
        400: "Bad Request",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
    }.get(int(status_code), "OK")

class SaaSControlPlaneRouter:
    """In-process REST-ish router for local tests and CLI smoke flows."""

    def __init__(self, service: SaaSControlPlaneService | None = None) -> None:
        self.service = service or SaaSControlPlaneService()

    def handle(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> JsonDict:
        method = method.upper()
        body = dict(body or {})
        parts = [part for part in path.strip("/").split("/") if part]
        try:
            if method == "POST" and parts == ["v1", "bootstrap"]:
                return {"status_code": 201, "body": self.service.bootstrap_project(**body)}
            if len(parts) >= 4 and parts[0] == "v1" and parts[1] == "projects":
                project_id = parts[2]
                tenant_id = str(body.get("tenant_id") or body.get("organization_id") or body.get("tenant") or "")
                if not tenant_id:
                    raise ValidationError("tenant_id is required")
                auth_key_id = body.get("auth_key_id") or body.get("api_key_id")
                if method == "POST" and len(parts) == 4 and parts[3] == "api-keys":
                    return {"status_code": 201, "body": self.service.create_api_key(tenant_id, project_id, name=str(body.get("name") or "API key"), scopes=list(body.get("scopes") or []), key_id=body.get("key_id"), auth_key_id=auth_key_id, reveal_secret=bool(body.get("reveal_secret", False)))}
                if method == "GET" and len(parts) == 4 and parts[3] == "api-keys":
                    return {"status_code": 200, "body": {"api_keys": self.service.list_api_keys(tenant_id, project_id, auth_key_id=auth_key_id)}}
                if method == "POST" and len(parts) == 6 and parts[3] == "api-keys" and parts[5] == "revoke":
                    return {"status_code": 200, "body": self.service.revoke_api_key(tenant_id, project_id, parts[4], auth_key_id=auth_key_id)}
                if method == "POST" and len(parts) == 6 and parts[3] == "api-keys" and parts[5] == "authenticate":
                    return {"status_code": 200, "body": self.service.authenticate_api_key(tenant_id, project_id, key_id=parts[4], scope=str(body.get("scope") or ""))}
                if method == "POST" and len(parts) == 6 and parts[3] == "api-keys" and parts[5] == "verify":
                    return {"status_code": 200, "body": self.service.verify_api_key_secret(tenant_id, project_id, key_id=parts[4], secret=str(body.get("secret") or ""), scope=body.get("scope"))}
                if method == "POST" and len(parts) == 6 and parts[3] == "api-keys" and parts[5] == "rate-limit":
                    return {"status_code": 200, "body": self.service.configure_api_key_rate_limit(tenant_id, project_id, key_id=parts[4], operation=str(body.get("operation") or "*"), limit=int(body.get("limit") or 0), period=str(body.get("period") or "local-window"), auth_key_id=auth_key_id)}
                if method == "GET" and len(parts) == 5 and parts[3] == "api-keys" and parts[4] == "rate-limits":
                    return {"status_code": 200, "body": self.service.api_key_rate_limit_snapshot(tenant_id, project_id, key_id=body.get("key_id"))}
                if method == "GET" and len(parts) == 4 and parts[3] == "audit-log":
                    limit = int(body["limit"]) if body.get("limit") not in {None, ""} else None
                    return {"status_code": 200, "body": self.service.audit_snapshot(tenant_id, project_id, auth_key_id=auth_key_id, action=body.get("action"), target_id=body.get("target_id"), api_key_id=body.get("audit_api_key_id"), limit=limit)}
                if method == "POST" and len(parts) == 5 and parts[3] == "audit-chain" and parts[4] == "verify":
                    limit = int(body["limit"]) if body.get("limit") not in {None, ""} else None
                    return {"status_code": 200, "body": self.service.verify_audit_chain_snapshot(tenant_id, project_id, auth_key_id=auth_key_id, action=body.get("action"), target_id=body.get("target_id"), api_key_id=body.get("audit_api_key_id"), limit=limit)}
                if method == "POST" and len(parts) == 4 and parts[3] == "sdk-submit":
                    return {"status_code": 202, "body": self.service.sdk_submit_run(tenant_id, project_id, dataset_id=str(body.get("dataset_id") or ""), agent_ref=str(body.get("agent_ref") or ""), run_id=body.get("run_id"), metadata=body.get("metadata") if isinstance(body.get("metadata"), Mapping) else None, api_key_id=auth_key_id, idempotency_key=body.get("idempotency_key"), request_id=body.get("request_id"))}
                if len(parts) >= 6 and parts[3] == "runs":
                    run_id = parts[4]
                    if method == "POST" and len(parts) == 6 and parts[5] == "upload":
                        result = body.get("result") if isinstance(body.get("result"), Mapping) else body
                        return {"status_code": 202, "body": self.service.upload_run_result(tenant_id, project_id, run_id, result, upload_id=body.get("upload_id"), api_key_id=auth_key_id, idempotency_key=body.get("idempotency_key"), request_id=body.get("request_id"))}
                    if method == "POST" and len(parts) == 6 and parts[5] == "trace-events":
                        observations = body.get("observations") if isinstance(body.get("observations"), list) else []
                        return {"status_code": 202, "body": self.service.ingest_trace(tenant_id, project_id, run_id, observations, batch_id=body.get("batch_id"), api_key_id=auth_key_id, idempotency_key=body.get("idempotency_key"), request_id=body.get("request_id"))}
                    if method == "GET" and len(parts) == 6 and parts[5] == "lifecycle":
                        return {"status_code": 200, "body": self.service.lifecycle_snapshot(tenant_id, project_id, run_id)}
                    if method == "POST" and len(parts) == 6 and parts[5] == "release-gate":
                        policy = body.get("policy") if isinstance(body.get("policy"), Mapping) else None
                        timeout_seconds = float(body.get("timeout_seconds") or 5.0)
                        return {"status_code": 200, "body": self.service.evaluate_release_gate(tenant_id, project_id, run_id, policy=policy, auth_key_id=auth_key_id, request_id=body.get("request_id"), idempotency_key=body.get("idempotency_key"), timeout_seconds=timeout_seconds)}
                    if method == "GET" and len(parts) == 6 and parts[5] == "release-evidence":
                        from .platform import build_release_evidence_packet, usage_billing_rollup

                        packet = build_release_evidence_packet(
                            tenant_id=tenant_id,
                            project_id=project_id,
                            run_id=run_id,
                            lifecycle=self.service.lifecycle_snapshot(tenant_id, project_id, run_id),
                            billing_rollup=usage_billing_rollup(list(self.service.store.usage_ledger.values()), tenant_id=tenant_id, project_id=project_id, billing_period="local"),
                            audit_chain=self.service.audit_snapshot(tenant_id, project_id, target_id=run_id).get("chain", {}),
                        )
                        return {"status_code": 200, "body": packet}
                    if method == "POST" and len(parts) == 7 and parts[5] == "release-evidence" and parts[6] == "verify":
                        packet = body.get("packet") if isinstance(body.get("packet"), Mapping) else None
                        if packet is None:
                            from .platform import build_release_evidence_packet, usage_billing_rollup

                            packet = build_release_evidence_packet(
                                tenant_id=tenant_id,
                                project_id=project_id,
                                run_id=run_id,
                                lifecycle=self.service.lifecycle_snapshot(tenant_id, project_id, run_id),
                                billing_rollup=usage_billing_rollup(list(self.service.store.usage_ledger.values()), tenant_id=tenant_id, project_id=project_id, billing_period="local"),
                                audit_chain=self.service.audit_snapshot(tenant_id, project_id, target_id=run_id).get("chain", {}),
                            )
                            source = "current_snapshot"
                        else:
                            source = "submitted_packet"
                        verification = self.service.verify_release_evidence_packet(tenant_id, project_id, packet, run_id=run_id, auth_key_id=auth_key_id)
                        return {"status_code": 200, "body": {**verification, "source": source}}
            raise ValidationError(f"unsupported route: {method} {path}")
        except Exception as exc:  # Public-safe local router envelope.
            code = getattr(exc, "code", "validation_error")
            status_code = 404 if code == "not_found" else 400
            return {"status_code": status_code, "body": {"schema_version": CONTROL_PLANE_SCHEMA_VERSION, "error": {"code": code, "message": str(exc)}}}


def snapshot_control_plane(service: SaaSControlPlaneService) -> JsonDict:
    payload = {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "state_schema_version": 2,
        "cloud": service.cloud.snapshot_state(),
        "metadata": {"local_only": True, "ashr_api_used": False},
        "state_metadata": {"writer": "services.api.control_plane", "updated_at": _utc_now()},
        "control_plane": {
            "api_keys": _jsonable(service.store.api_keys),
            "api_key_rate_limits": _jsonable(service.store.api_key_rate_limits),
            "uploads": _jsonable(service.store.uploads),
            "trace_batches": _jsonable(service.store.trace_batches),
            "sdk_submissions": _jsonable(service.store.sdk_submissions),
            "audit_log": _jsonable(service.store.audit_log),
            "usage_ledger": _jsonable(service.store.usage_ledger),
            "idempotency_keys": _jsonable(service.store.idempotency_keys),
        },
    }
    payload["integrity"] = {"payload_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()}
    return payload


def write_control_plane_state(service: SaaSControlPlaneService, path: str) -> str:
    from pathlib import Path

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(json.dumps(snapshot_control_plane(service), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(output)
    return str(output)


def control_plane_from_state(payload: Mapping[str, Any]) -> SaaSControlPlaneService:
    state_version = int(payload.get("state_schema_version", 1))
    if state_version not in {1, 2}:
        raise ValidationError(f"unsupported control-plane state schema version: {state_version}")
    cloud_payload = payload.get("cloud") if isinstance(payload.get("cloud"), Mapping) else {}
    control_payload = payload.get("control_plane") if isinstance(payload.get("control_plane"), Mapping) else {}
    cloud = CloudApiService.from_state(cloud_payload)
    store = SaaSControlPlaneStore(
        api_keys=dict(control_payload.get("api_keys") or {}),
        api_key_rate_limits=dict(control_payload.get("api_key_rate_limits") or {}),
        uploads=dict(control_payload.get("uploads") or {}),
        trace_batches=dict(control_payload.get("trace_batches") or {}),
        sdk_submissions=dict(control_payload.get("sdk_submissions") or {}),
        audit_log=dict(control_payload.get("audit_log") or {}),
        usage_ledger=dict(control_payload.get("usage_ledger") or {}),
        idempotency_keys=dict(control_payload.get("idempotency_keys") or {}),
    )
    return SaaSControlPlaneService(cloud, store=store)


def control_plane_from_state_file(path: str) -> SaaSControlPlaneService:
    from pathlib import Path

    return control_plane_from_state(json.loads(Path(path).read_text(encoding="utf-8")))
