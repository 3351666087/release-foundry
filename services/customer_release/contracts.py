"""Verification contract for a Customer Agent Release.

The customer release is downstream of both product readiness and the A2
Decision Ledger. It verifies references and preserves upstream authority; it
never recomputes a score, grade, failure class, or release decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


CUSTOMER_AGENT_RELEASE_MANIFEST_SCHEMA = "ashr.customer_agent_release_manifest.v1"
CUSTOMER_AGENT_RELEASE_VERIFICATION_SCHEMA = "ashr.customer_agent_release_verification.v1"

_AGENT_RELEASE_ID_RE = re.compile(
    r"^agent-release:[a-z0-9][a-z0-9-]{0,62}/[a-z0-9][a-z0-9-]{0,62}@"
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_PRODUCT_RELEASE_ID_RE = re.compile(
    r"^ashr-product@"
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HASH_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCOPE_FIELDS = (
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id",
)
_SAFE_SECRET_SENTINELS = {"", "redacted", "[redacted]", "<redacted>", "not-set", "none"}
_SENSITIVE_KEY_PARTS = ("password", "private_key", "secret", "token")


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    path: str
    message: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


class _Verifier:
    def __init__(self, manifest_path: Path, release_root: Path | None) -> None:
        self.manifest_path = manifest_path.resolve()
        self.release_root = (release_root or manifest_path.parent).resolve()
        self.issues: list[VerificationIssue] = []
        self.checked_evidence_ids: list[str] = []
        self.product_release_decision: str | None = None
        self.a2_authoritative_decision: str | None = None

    def issue(self, code: str, path: str, message: str) -> None:
        self.issues.append(VerificationIssue(code=code, path=path, message=message))

    def mapping(self, value: Any, path: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            self.issue("invalid_type", path, "must be an object")
            return {}
        return value

    def resolve_ref(
        self,
        value: Any,
        path: str,
        *,
        load_json: bool = False,
    ) -> tuple[Path | None, Any]:
        ref = self.mapping(value, path)
        raw_path = ref.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            self.issue("missing_path", f"{path}.path", "must be a release-relative path")
            return None, None
        if "\\" in raw_path:
            self.issue("non_portable_path", f"{path}.path", "must use forward slashes")
            return None, None
        portable = PurePosixPath(raw_path)
        if portable.is_absolute() or ".." in portable.parts:
            self.issue("unsafe_path", f"{path}.path", "must remain inside the release bundle")
            return None, None
        resolved = (self.release_root / Path(*portable.parts)).resolve()
        if resolved != self.release_root and self.release_root not in resolved.parents:
            self.issue("unsafe_path", f"{path}.path", "resolved path escapes the release bundle")
            return None, None
        expected_hash = ref.get("sha256")
        if not isinstance(expected_hash, str) or not _SHA256_RE.fullmatch(expected_hash):
            self.issue("invalid_evidence_digest", f"{path}.sha256", "must be lowercase SHA-256")
        try:
            raw = resolved.read_bytes()
        except OSError as exc:
            self.issue("missing_evidence_file", f"{path}.path", str(exc))
            return resolved, None
        if isinstance(expected_hash, str) and _sha256_bytes(raw) != expected_hash:
            self.issue("evidence_digest_mismatch", path, "file digest does not match manifest")
        if not load_json:
            return resolved, None
        try:
            return resolved, json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.issue("invalid_json_evidence", f"{path}.path", str(exc))
            return resolved, None

    def verify_source(self, manifest: Mapping[str, Any]) -> str:
        source = self.mapping(manifest.get("source"), "source")
        if not isinstance(source.get("repository"), str) or not source.get("repository"):
            self.issue("missing_repository", "source.repository", "must identify the release source")
        commit = source.get("commit_sha")
        if not isinstance(commit, str) or not _COMMIT_RE.fullmatch(commit):
            self.issue("invalid_commit", "source.commit_sha", "must be a 40- or 64-character Git SHA")
            commit = ""
        if source.get("dirty") is not False:
            self.issue("dirty_source", "source.dirty", "release source must be clean")
        return str(commit)

    def verify_scope(self, manifest: Mapping[str, Any]) -> Mapping[str, Any]:
        scope = self.mapping(manifest.get("tenant_scope"), "tenant_scope")
        for field in _SCOPE_FIELDS:
            value = scope.get(field)
            if not isinstance(value, str) or not value.strip():
                self.issue("incomplete_tenant_scope", f"tenant_scope.{field}", "must be non-empty")
        return scope

    def verify_candidate(self, manifest: Mapping[str, Any], source_commit: str) -> Mapping[str, Any]:
        candidate = self.mapping(manifest.get("candidate"), "candidate")
        for field in ("agent_id", "version", "candidate_id", "run_id", "evidence_release_version"):
            if not isinstance(candidate.get(field), str) or not candidate.get(field):
                self.issue("incomplete_candidate_identity", f"candidate.{field}", "must be non-empty")
        if candidate.get("source_commit") != source_commit:
            self.issue("candidate_source_mismatch", "candidate.source_commit", "must match release source")
        return candidate

    def verify_product_binding(self, manifest: Mapping[str, Any], source_commit: str) -> None:
        binding = self.mapping(manifest.get("product_binding"), "product_binding")
        release_id = binding.get("product_release_id")
        expected_manifest_hash = binding.get("product_release_manifest_sha256")
        if not isinstance(release_id, str) or not _PRODUCT_RELEASE_ID_RE.fullmatch(release_id):
            self.issue("invalid_product_release_id", "product_binding.product_release_id", "must be canonical")
        if not isinstance(expected_manifest_hash, str) or not _SHA256_RE.fullmatch(expected_manifest_hash):
            self.issue(
                "invalid_product_manifest_digest",
                "product_binding.product_release_manifest_sha256",
                "must be lowercase SHA-256",
            )

        product_manifest_path, product_manifest = self.resolve_ref(
            binding.get("manifest"),
            "product_binding.manifest",
            load_json=True,
        )
        _, product_verification = self.resolve_ref(
            binding.get("verification"),
            "product_binding.verification",
            load_json=True,
        )
        if product_manifest_path is not None and product_manifest_path.exists():
            actual_hash = _sha256_bytes(product_manifest_path.read_bytes())
            if actual_hash != expected_manifest_hash:
                self.issue(
                    "product_manifest_binding_mismatch",
                    "product_binding.product_release_manifest_sha256",
                    "does not match the bound Product Release manifest",
                )
        if isinstance(product_manifest, Mapping) and product_manifest.get("product_release_id") != release_id:
            self.issue("product_release_id_mismatch", "product_binding.manifest", "release id differs")
        if isinstance(product_manifest, Mapping):
            product_source = self.mapping(product_manifest.get("source"), "product_binding.manifest.source")
            if product_source.get("commit_sha") != source_commit:
                self.issue(
                    "product_source_mismatch",
                    "product_binding.manifest.source.commit_sha",
                    "Product and Customer releases must bind the same source commit",
                )
        if not isinstance(product_verification, Mapping):
            return
        self.product_release_decision = str(product_verification.get("decision") or "")
        if product_verification.get("schema_version") != "ashr.product_release_verification.v1":
            self.issue("unsupported_product_verification", "product_binding.verification", "schema mismatch")
        if product_verification.get("product_release_id") != release_id:
            self.issue("product_release_id_mismatch", "product_binding.verification", "release id differs")
        if product_verification.get("product_release_manifest_sha256") != expected_manifest_hash:
            self.issue("product_manifest_binding_mismatch", "product_binding.verification", "digest differs")
        if product_verification.get("decision") != "approve_product_release":
            self.issue(
                "product_release_not_approved",
                "product_binding.verification.decision",
                "Customer Agent Release requires an approved Product Release",
            )

    def evidence_json(self, evidence: Mapping[str, Any], evidence_id: str) -> Mapping[str, Any]:
        _, value = self.resolve_ref(evidence.get(evidence_id), f"evidence.{evidence_id}", load_json=True)
        self.checked_evidence_ids.append(evidence_id)
        return value if isinstance(value, Mapping) else {}

    def verify_evidence(
        self,
        manifest: Mapping[str, Any],
        scope: Mapping[str, Any],
        candidate: Mapping[str, Any],
        source_commit: str,
    ) -> None:
        evidence = self.mapping(manifest.get("evidence"), "evidence")
        a1 = self.evidence_json(evidence, "a1_run_result")
        if a1.get("schema_version") != "ashr.clone.run_result.v1":
            self.issue("unsupported_a1_evidence", "evidence.a1_run_result", "schema mismatch")
        if a1.get("run_id") != candidate.get("run_id"):
            self.issue("a1_run_mismatch", "evidence.a1_run_result", "run id differs from candidate")
        if a1.get("status") != "passed":
            self.issue("a1_run_not_passed", "evidence.a1_run_result.status", "must be passed")

        a2 = self.evidence_json(evidence, "a2_trusted_spine")
        if a2.get("schema_version") != "a2.trusted_spine_handoff.v1":
            self.issue("unsupported_a2_evidence", "evidence.a2_trusted_spine", "schema mismatch")
        snapshot = self.mapping(a2.get("evidence_snapshot"), "evidence.a2_trusted_spine.snapshot")
        ledger = self.mapping(a2.get("decision_ledger"), "evidence.a2_trusted_spine.ledger")
        consumption = self.mapping(a2.get("a3_consumption"), "evidence.a2_trusted_spine.a3_consumption")
        if snapshot.get("run_id") != candidate.get("run_id"):
            self.issue(
                "a2_candidate_run_mismatch",
                "evidence.a2_trusted_spine.snapshot.run_id",
                "A2 evidence must be bound to the Customer Agent candidate run",
            )
        for field in _SCOPE_FIELDS:
            if snapshot.get(field) != scope.get(field) or ledger.get(field) != scope.get(field):
                self.issue("evidence_scope_mismatch", f"evidence.a2_trusted_spine.{field}", "scope differs")
        records = ledger.get("records") if isinstance(ledger.get("records"), list) else []
        if not records or not isinstance(records[-1], Mapping):
            self.issue("a2_decision_missing", "evidence.a2_trusted_spine.ledger.records", "must be non-empty")
        else:
            latest = records[-1]
            decision = str(latest.get("decision") or "")
            self.a2_authoritative_decision = decision
            if latest.get("run_id") != candidate.get("run_id"):
                self.issue(
                    "a2_candidate_run_mismatch",
                    "evidence.a2_trusted_spine.ledger.records[-1].run_id",
                    "A2 Decision Ledger must be bound to the Customer Agent candidate run",
                )
            if latest.get("record_hash") != ledger.get("head_hash"):
                self.issue("a2_ledger_head_mismatch", "evidence.a2_trusted_spine.ledger", "head hash differs")
            if decision not in {"allow", "approve", "release_ready"}:
                self.issue("a2_release_blocked", "evidence.a2_trusted_spine.decision", f"A2 decision is {decision!r}")
            if consumption.get("display_provenance_hash") != latest.get("record_hash"):
                self.issue("a2_provenance_mismatch", "evidence.a2_trusted_spine.a3_consumption", "hash differs")
        if self.mapping(ledger.get("metadata"), "evidence.a2_trusted_spine.ledger.metadata").get("chain_verified") is not True:
            self.issue("a2_ledger_unverified", "evidence.a2_trusted_spine.ledger.metadata", "chain must verify")
        if consumption.get("release_ready") is not True:
            self.issue("a2_release_not_ready", "evidence.a2_trusted_spine.a3_consumption", "release_ready must be true")

        gate = self.evidence_json(evidence, "a3_gate_report")
        if gate.get("schema_version") != "a3.gate_cli.v1":
            self.issue("unsupported_a3_gate", "evidence.a3_gate_report", "schema mismatch")
        if self.mapping(gate.get("release_gate"), "evidence.a3_gate_report.release_gate").get("decision") != "approve_release":
            self.issue("a3_gate_blocked", "evidence.a3_gate_report.release_gate", "must approve release")
        gate_workflow = self.mapping(gate.get("release_workflow"), "evidence.a3_gate_report.release_workflow")
        self.verify_release_version(gate_workflow, candidate, "evidence.a3_gate_report.release_workflow")

        artifact_verification = self.evidence_json(evidence, "a3_release_artifact_verification")
        if artifact_verification.get("schema_version") != "a3.release_artifact_verification.v1":
            self.issue("unsupported_a3_artifact_verification", "evidence.a3_release_artifact_verification", "schema mismatch")
        if artifact_verification.get("status") != "passed":
            self.issue("a3_artifact_integrity_failed", "evidence.a3_release_artifact_verification.status", "must pass")
        self.verify_release_version(
            artifact_verification,
            candidate,
            "evidence.a3_release_artifact_verification",
        )

        delivery = self.evidence_json(evidence, "a3_release_delivery_index")
        if delivery.get("schema_version") != "a3.release_delivery_index.v1":
            self.issue("unsupported_a3_delivery", "evidence.a3_release_delivery_index", "schema mismatch")
        if delivery.get("production_ready") is not True:
            self.issue("a3_delivery_not_ready", "evidence.a3_release_delivery_index.production_ready", "must be true")
        self.verify_release_version(delivery, candidate, "evidence.a3_release_delivery_index")
        for field in ("git_sha_alias", "ci_tested_sha_alias"):
            if delivery.get(field) != source_commit:
                self.issue(
                    "a3_delivery_source_mismatch",
                    f"evidence.a3_release_delivery_index.{field}",
                    "A3 delivery evidence must be rebuilt and tested from the release source commit",
                )
        delivery_authority = self.mapping(
            delivery.get("authority"),
            "evidence.a3_release_delivery_index.authority",
        )
        a1_run_ids = delivery_authority.get("a1_run_ids")
        if not isinstance(a1_run_ids, list) or candidate.get("run_id") not in a1_run_ids:
            self.issue(
                "a3_delivery_run_mismatch",
                "evidence.a3_release_delivery_index.authority.a1_run_ids",
                "A3 delivery evidence must include the Customer Agent candidate run",
            )

        bundle = self.evidence_json(evidence, "a3_audit_bundle_index")
        if bundle.get("schema_version") != "a3.audit_bundle_index.v1":
            self.issue("unsupported_a3_audit_bundle", "evidence.a3_audit_bundle_index", "schema mismatch")
        self.verify_release_identity(
            self.mapping(bundle.get("release"), "evidence.a3_audit_bundle_index.release"),
            candidate,
            "evidence.a3_audit_bundle_index.release",
        )
        archive = self.evidence_json(evidence, "a3_audit_archive_manifest")
        if archive.get("schema_version") != "a3.audit_archive_manifest.v1":
            self.issue("unsupported_a3_audit_archive", "evidence.a3_audit_archive_manifest", "schema mismatch")
        archive_bundle = self.mapping(
            archive.get("bundle"),
            "evidence.a3_audit_archive_manifest.bundle",
        )
        self.verify_release_identity(
            self.mapping(archive_bundle.get("release"), "evidence.a3_audit_archive_manifest.bundle.release"),
            candidate,
            "evidence.a3_audit_archive_manifest.bundle.release",
        )

    def verify_release_version(
        self,
        value: Mapping[str, Any],
        candidate: Mapping[str, Any],
        path: str,
    ) -> None:
        if value.get("release_version") != candidate.get("evidence_release_version"):
            self.issue(
                "a3_release_version_mismatch",
                f"{path}.release_version",
                "A3 evidence release version differs from the Customer Agent candidate",
            )

    def verify_release_identity(
        self,
        value: Mapping[str, Any],
        candidate: Mapping[str, Any],
        path: str,
    ) -> None:
        if value.get("run_id") != candidate.get("run_id"):
            self.issue(
                "a3_audit_run_mismatch",
                f"{path}.run_id",
                "A3 audit evidence must be bound to the Customer Agent candidate run",
            )
        self.verify_release_version(value, candidate, path)

    def verify_human_review(
        self,
        manifest: Mapping[str, Any],
        release_id: str,
        candidate: Mapping[str, Any],
        source_commit: str,
    ) -> None:
        review = self.mapping(manifest.get("human_review"), "human_review")
        if review.get("status") != "approved":
            self.issue("human_approval_missing", "human_review.status", "must be approved")
            return
        _, receipt_value = self.resolve_ref(
            review.get("approval_receipt"),
            "human_review.approval_receipt",
            load_json=True,
        )
        receipt = self.mapping(receipt_value, "human_review.approval_receipt.content")
        expected = {
            "schema_version": "a3.review_approval.v1",
            "status": "approved",
            "agent_release_id": release_id,
            "candidate_id": candidate.get("candidate_id"),
            "source_commit": source_commit,
        }
        for field, expected_value in expected.items():
            if receipt.get(field) != expected_value:
                self.issue(
                    "invalid_human_approval",
                    f"human_review.approval_receipt.content.{field}",
                    "approval receipt is not bound to this release candidate",
                )
        if not _HASH_REF_RE.fullmatch(str(receipt.get("reviewer_identity_hash") or "")):
            self.issue(
                "invalid_human_approval",
                "human_review.approval_receipt.content.reviewer_identity_hash",
                "must be a pseudonymous SHA-256 reviewer identity",
            )
        if _parse_rfc3339(receipt.get("approved_at")) is None:
            self.issue(
                "invalid_human_approval",
                "human_review.approval_receipt.content.approved_at",
                "must be a timezone-aware RFC 3339 timestamp",
            )

    def scan_secret_material(self, value: Any, path: str = "$") -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                lowered = str(key).lower()
                if (
                    isinstance(child, str)
                    and any(part in lowered for part in _SENSITIVE_KEY_PARTS)
                    and child.strip().lower() not in _SAFE_SECRET_SENTINELS
                    and not child.startswith(("env:", "vault:", "secret:"))
                ):
                    self.issue("embedded_secret_material", child_path, "only secret references are allowed")
                self.scan_secret_material(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self.scan_secret_material(child, f"{path}[{index}]")

    def verify(self) -> dict[str, Any]:
        try:
            raw = self.manifest_path.read_bytes()
            manifest = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.issue("manifest_read_failed", "$", str(exc))
            return self.result(None, None)
        manifest = self.mapping(manifest, "$")
        manifest_hash = _sha256_bytes(raw)
        if manifest.get("schema_version") != CUSTOMER_AGENT_RELEASE_MANIFEST_SCHEMA:
            self.issue("unsupported_manifest_schema", "schema_version", "schema mismatch")
        release_id = manifest.get("agent_release_id")
        if not isinstance(release_id, str) or not _AGENT_RELEASE_ID_RE.fullmatch(release_id):
            self.issue("invalid_agent_release_id", "agent_release_id", "must be canonical")
            release_id = str(release_id or "")
        if _parse_rfc3339(manifest.get("generated_at")) is None:
            self.issue("invalid_timestamp", "generated_at", "must be timezone-aware RFC 3339")
        self.scan_secret_material(manifest)
        source_commit = self.verify_source(manifest)
        scope = self.verify_scope(manifest)
        candidate = self.verify_candidate(manifest, source_commit)
        self.verify_product_binding(manifest, source_commit)
        self.verify_evidence(manifest, scope, candidate, source_commit)
        self.verify_human_review(manifest, release_id, candidate, source_commit)
        authority = self.mapping(manifest.get("authority"), "authority")
        if authority.get("a3_recomputed_a2_decision") is not False:
            self.issue("a3_authority_overreach", "authority.a3_recomputed_a2_decision", "must be false")
        if authority.get("decision_authority") != "A2 Decision Ledger":
            self.issue("invalid_decision_authority", "authority.decision_authority", "must remain A2")
        return self.result(release_id or None, manifest_hash)

    def result(self, release_id: str | None, manifest_hash: str | None) -> dict[str, Any]:
        issues = sorted(self.issues, key=lambda item: (item.code, item.path, item.message))
        approved = not issues
        return {
            "schema_version": CUSTOMER_AGENT_RELEASE_VERIFICATION_SCHEMA,
            "decision": "approve_customer_agent_release" if approved else "block_customer_agent_release",
            "agent_release_id": release_id,
            "agent_release_manifest_sha256": manifest_hash,
            "product_release_decision": self.product_release_decision,
            "a2_authoritative_decision": self.a2_authoritative_decision,
            "a3_recomputed_a2_decision": False,
            "checked_evidence_ids": sorted(set(self.checked_evidence_ids)),
            "blocking_reasons": sorted({item.code for item in issues}),
            "issues": [asdict(item) for item in issues],
        }


def verify_customer_agent_release_manifest(
    manifest_path: str | Path,
    *,
    release_root: str | Path | None = None,
) -> dict[str, Any]:
    """Verify a Customer Agent Release manifest without changing A2 authority."""

    path = Path(manifest_path)
    root = Path(release_root) if release_root is not None else None
    return _Verifier(path, root).verify()
