"""Run a public-safe, local-only A1 self-host readiness probe for A3."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.sdk.ashr_clone.storage import LocalFilesystemObjectStorage
from services.api.control_plane import SaaSControlPlaneService, create_control_plane_wsgi_app


SCHEMA_VERSION = "a3.a1_self_host_sandbox_probe.v1"
TENANT_ID = "tenant-a3-sandbox"
PROJECT_ID = "project-a3-sandbox"
RUN_ID = "run-a3-sandbox"


def run_probe(*, observed_at: str | None = None) -> dict[str, Any]:
    """Exercise A1 local runtime behavior without external APIs or secret material."""

    observed_at = observed_at or _utc_now()
    checks = [
        _health_check(),
        _worker_retry_check(),
        _worker_lease_recovery_check(),
        _object_storage_check(),
    ]
    passed = sum(item["status"] == "passed" for item in checks)
    failed = len(checks) - passed
    production_gaps = _production_gaps()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "calibration_id": "a1-local-self-host-20260713",
        "observed_at": observed_at,
        "status": "sandbox_verified" if failed == 0 else "sandbox_failed",
        "source_lane": "A1",
        "probe_owner": "A3",
        "execution_mode": "local_process",
        "external_api_used": False,
        "tenant_scope": {
            "organization_id": "org-local",
            "tenant_id": "tenant-local",
            "workspace_id": "workspace-local",
            "project_id": "project-local",
            "environment_id": "staging",
        },
        "summary": {
            "total_checks": len(checks),
            "passed": passed,
            "failed": failed,
            "production_gap_count": len(production_gaps),
        },
        "checks": checks,
        "production_gaps": production_gaps,
        "authority_boundary": {
            "evidence_level": "sandbox_verified" if failed == 0 else "sandbox_failed",
            "production_verified": False,
            "deployment_acceptance_mutated": False,
            "release_ready_mutated": False,
            "a2_decision_recomputed": False,
            "a2_release_decision_authority": "A2",
        },
        "safety": {
            "local_only": True,
            "raw_payload_included": False,
            "credential_material_included": False,
            "absolute_local_path_included": False,
            "external_network_used": False,
            "ashr_api_used": False,
        },
    }
    return payload


def _health_check() -> dict[str, Any]:
    response = create_control_plane_wsgi_app().handle_environ(
        {"REQUEST_METHOD": "GET", "PATH_INFO": "/healthz"}
    )
    body = response.get("body") or {}
    passed = (
        response.get("status_code") == 200
        and body.get("status") == "ok"
        and body.get("local_only") is True
        and body.get("ashr_api_used") is False
    )
    return _check(
        "a1_control_plane_health",
        "A1 local control-plane health",
        passed,
        {
            "http_status": response.get("status_code"),
            "service": body.get("service"),
            "service_status": body.get("status"),
            "local_only": body.get("local_only") is True,
            "external_api_used": body.get("ashr_api_used") is True,
        },
        "services.api.control_plane.create_control_plane_wsgi_app",
    )


def _worker_retry_check() -> dict[str, Any]:
    control = _control_plane()
    queued = control.enqueue_worker_job(
        TENANT_ID,
        PROJECT_ID,
        job_type="release.evidence.verify",
        target_id=RUN_ID,
        payload={"run_id": RUN_ID, "evidence_ref": "sandbox-calibration"},
        job_id="job-a3-retry",
        priority=5,
        max_attempts=2,
        idempotency_key="a3-sandbox-retry",
    )
    first_lease = control.lease_worker_job(
        TENANT_ID,
        PROJECT_ID,
        lease_owner_id="worker-a3-one",
        lease_seconds=30,
    )
    heartbeat = control.heartbeat_worker_job(
        TENANT_ID,
        PROJECT_ID,
        queued["job_id"],
        lease_owner_id="worker-a3-one",
        lease_seconds=30,
    )
    retrying = control.fail_worker_job(
        TENANT_ID,
        PROJECT_ID,
        queued["job_id"],
        {"type": "SandboxTransientError", "message": "public-safe calibration failure"},
        lease_owner_id="worker-a3-one",
        retry_after_seconds=0,
    )
    second_lease = control.lease_worker_job(
        TENANT_ID,
        PROJECT_ID,
        lease_owner_id="worker-a3-two",
        lease_seconds=30,
    )
    dead_lettered = control.fail_worker_job(
        TENANT_ID,
        PROJECT_ID,
        queued["job_id"],
        {"type": "SandboxPermanentError"},
        lease_owner_id="worker-a3-two",
    )
    listed = control.list_worker_jobs(TENANT_ID, PROJECT_ID, status="dead_lettered")
    audit_actions = {
        item.get("action") for item in control.audit_snapshot(TENANT_ID, PROJECT_ID).get("events", [])
    }
    passed = all(
        [
            queued.get("status") == "queued",
            first_lease.get("leased") is True,
            heartbeat.get("status") == "leased",
            retrying.get("status") == "retrying",
            (second_lease.get("job") or {}).get("attempts") == 2,
            dead_lettered.get("status") == "dead_lettered",
            listed.get("count") == 1,
            {"worker.job.enqueue", "worker.job.lease", "worker.job.heartbeat", "worker.job.fail"}
            <= audit_actions,
        ]
    )
    return _check(
        "a1_worker_retry_dead_letter",
        "A1 worker retry, heartbeat, and dead-letter lifecycle",
        passed,
        {
            "state_sequence": [
                queued.get("status"),
                first_lease.get("status"),
                retrying.get("status"),
                dead_lettered.get("status"),
            ],
            "attempts": (second_lease.get("job") or {}).get("attempts"),
            "dead_letter_count": listed.get("count"),
            "audit_action_count": len(audit_actions),
            "raw_job_payload_exposed": queued.get("raw_payload_included") is True,
        },
        "services.api.control_plane.SaaSControlPlaneService",
    )


def _worker_lease_recovery_check() -> dict[str, Any]:
    control = _control_plane()
    queued = control.enqueue_worker_job(
        TENANT_ID,
        PROJECT_ID,
        job_type="trace.compact",
        target_id=RUN_ID,
        job_id="job-a3-expired-lease",
        max_attempts=2,
    )
    first = control.lease_worker_job(
        TENANT_ID,
        PROJECT_ID,
        lease_owner_id="worker-a3-old",
        lease_seconds=1,
    )
    control.store.worker_jobs[queued["job_id"]]["lease_expires_at"] = "2000-01-01T00:00:00.000Z"
    recovered = control.lease_worker_job(
        TENANT_ID,
        PROJECT_ID,
        lease_owner_id="worker-a3-recovery",
        lease_seconds=1,
    )
    recovered_job = recovered.get("job") or {}
    passed = (
        first.get("leased") is True
        and recovered.get("leased") is True
        and recovered_job.get("lease_owner_id") == "worker-a3-recovery"
        and recovered_job.get("attempts") == 2
    )
    return _check(
        "a1_worker_expired_lease_recovery",
        "A1 worker expired-lease recovery",
        passed,
        {
            "initial_lease_acquired": first.get("leased") is True,
            "expired_lease_recovered": recovered.get("leased") is True,
            "recovery_attempt": recovered_job.get("attempts"),
            "recovery_owner_alias": recovered_job.get("lease_owner_id"),
        },
        "services.api.control_plane.SaaSControlPlaneService",
    )


def _object_storage_check() -> dict[str, Any]:
    content = b"A3 local self-host sandbox object evidence\n"
    with tempfile.TemporaryDirectory(prefix="a3-self-host-sandbox-") as root:
        storage = LocalFilesystemObjectStorage(root)
        manifest = storage.write_object(
            tenant_id=TENANT_ID,
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            object_id="object-a3-sandbox",
            content=content,
            content_type="application/octet-stream",
            category="calibration",
            suffix=".bin",
            metadata={"purpose": "a3-self-host-sandbox"},
        )
        verified = storage.verify_object(manifest)
        object_path = Path(root) / str(manifest["object_key"])
        object_path.write_bytes(b"tampered sandbox object\n")
        tampered = storage.verify_object(manifest)

    tamper_reasons = sorted({item.get("reason") for item in tampered.get("failures", [])})
    passed = (
        verified.get("verified") is True
        and tampered.get("verified") is False
        and "sha256_mismatch" in tamper_reasons
        and manifest.get("raw_payload_included") is False
        and manifest.get("secret_value_present") is False
    )
    return _check(
        "a1_local_object_storage_integrity",
        "A1 local object write, readback, and tamper detection",
        passed,
        {
            "backend": manifest.get("backend"),
            "size_bytes": manifest.get("size_bytes"),
            "write_readback_verified": verified.get("verified") is True,
            "tamper_detected": tampered.get("verified") is False,
            "tamper_failure_classes": tamper_reasons,
            "content_sha256_alias": f"sha256:{hashlib.sha256(content).hexdigest()}",
            "raw_payload_exposed": manifest.get("raw_payload_included") is True,
        },
        "packages.sdk.ashr_clone.storage.LocalFilesystemObjectStorage",
    )


def _control_plane() -> SaaSControlPlaneService:
    control = SaaSControlPlaneService()
    control.bootstrap_project(
        tenant_name="A3 Sandbox Tenant",
        project_name="A3 Sandbox Project",
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
    )
    return control


def _check(
    check_id: str,
    label: str,
    passed: bool,
    observed: dict[str, Any],
    contract_source: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "status": "passed" if passed else "failed",
        "evidence_level": "sandbox_verified" if passed else "sandbox_failed",
        "contract_source": contract_source,
        "observed": observed,
        "production_proof": False,
    }


def _production_gaps() -> list[dict[str, str]]:
    return [
        {
            "id": "postgres_rls_tenant_isolation",
            "status": "not_run",
            "reason": "A local PostgreSQL qualification cannot prove the target customer environment.",
            "required_evidence": "Two-tenant PostgreSQL/RLS negative test receipt from the target environment.",
        },
        {
            "id": "container_image_identity",
            "status": "not_run",
            "reason": "Docker and Podman are unavailable in this workspace.",
            "required_evidence": "Signed image digest and runtime image readback from the target environment.",
        },
        {
            "id": "vpc_network_policy",
            "status": "not_run",
            "reason": "This local process cannot prove customer VPC ingress, egress, or service identity.",
            "required_evidence": "Target VPC network-policy and service-identity probe receipt.",
        },
        {
            "id": "upgrade_rollback_recovery",
            "status": "not_run",
            "reason": "No authorized production-like installation is available for upgrade or rollback.",
            "required_evidence": "Versioned upgrade, forced-failure, rollback, and recovery receipt.",
        },
        {
            "id": "production_a2_release_authority",
            "status": "not_run",
            "reason": "A3 sandbox validation does not create or change an A2 Decision Ledger record.",
            "required_evidence": "Same-candidate A2 Trusted Spine with an authoritative release decision.",
        },
    ]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the A1-backed A3 self-host sandbox probe.")
    parser.add_argument("--observed-at")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv if argv is not None else sys.argv[1:]))
    try:
        payload = run_probe(observed_at=args.observed_at)
    except Exception as error:  # pragma: no cover - CLI fail-closed boundary
        failure = {
            "schema_version": "a3.a1_self_host_sandbox_probe_error.v1",
            "error": "sandbox_probe_failed",
            "error_class": type(error).__name__,
            "message": "A1 local sandbox probe failed; no production state changed.",
            "safety": {"exception_message_exposed": False, "credential_material_included": False},
        }
        sys.stderr.write(f"{json.dumps(failure, sort_keys=True)}\n")
        return 1
    sys.stdout.write(f"{json.dumps(payload, sort_keys=True)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
