"""Public-safe A1 evidence snapshots for the A2 trusted evidence spine.

This module intentionally does not import A2.  It implements the published
``a2.evidence_snapshot.v1`` wire contract at the A1 ownership boundary and
accepts hash-only evidence facts.  Raw artifact bytes and private evidence
paths must be resolved and hashed before this producer is called.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence


EVIDENCE_SNAPSHOT_SCHEMA_VERSION = "a2.evidence_snapshot.v1"
EXTRACTOR_ID = "a1.trusted_evidence_producer"
EXTRACTOR_VERSION = "1.0.0"
REFERENCE_HASH_SCHEMA_VERSION = "releasefoundry.trusted_evidence_reference.v1"
DEFAULT_MAX_BATCH_SIZE = 80
DEFAULT_MAX_ARTIFACTS_PER_SNAPSHOT = 2_048
DEFAULT_MAX_TOOL_CALLS_PER_SNAPSHOT = 4_096

MODALITIES = ("audio", "file", "image", "text", "video")
COLLECTION_STATUSES = ("complete", "evidence_missing", "invalid", "partial")
COMPLETENESS_STATUSES = frozenset(COLLECTION_STATUSES)

_HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:+-]{0,255}$")
_TOOL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SCHEMA_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ENCODED_TRAVERSAL_RE = re.compile(r"%(?:2e|2f|5c)", re.IGNORECASE)
_SECRET_SHAPED_IDENTIFIER_RE = re.compile(
    r"(?:^|[_.:+-])(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|private[_-]?key|password|passwd|secret)(?:$|[_.:+-])",
    re.IGNORECASE,
)

_SNAPSHOT_KEYS = frozenset(
    {
        "schema_version",
        "snapshot_id",
        "snapshot_hash",
        "organization_id",
        "tenant_id",
        "workspace_id",
        "project_id",
        "environment_id",
        "run_id",
        "case_id",
        "scenario_id",
        "created_at",
        "source_schema_version",
        "source_payload_hash",
        "required_modalities",
        "observed_modalities",
        "completeness",
        "missing_modalities",
        "tool_call_count",
        "tool_sequence",
        "artifacts",
        "extractor_provenance",
        "security",
    }
)
_ARTIFACT_KEYS = frozenset(
    {
        "artifact_id",
        "modality",
        "producer_tool",
        "reference_hash",
        "content_hash",
        "content_included",
        "collection_status",
    }
)
_PROVENANCE_KEYS = frozenset(
    {"extractor_id", "extractor_version", "input_hash", "status"}
)
_SECURITY = {
    "tenant_scoped": True,
    "scope_complete": True,
    "raw_evidence_included": False,
    "private_evidence_included": False,
    "secrets_included": False,
    "artifact_content_included": False,
}


class TrustedEvidenceError(ValueError):
    """Raised when evidence cannot cross the public A1 -> A2 boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EvidenceBinding:
    """The immutable organization-to-scenario evidence scope."""

    organization_id: str
    tenant_id: str
    workspace_id: str
    project_id: str
    environment_id: str
    run_id: str
    case_id: str
    scenario_id: str

    def __post_init__(self) -> None:
        for name, value in self.as_dict().items():
            _validate_opaque_identifier(value, name)

    def as_dict(self) -> dict[str, str]:
        return {
            "organization_id": self.organization_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "environment_id": self.environment_id,
            "run_id": self.run_id,
            "case_id": self.case_id,
            "scenario_id": self.scenario_id,
        }

    def key(self) -> tuple[str, str, str, str, str, str, str, str]:
        return (
            self.organization_id,
            self.tenant_id,
            self.workspace_id,
            self.project_id,
            self.environment_id,
            self.run_id,
            self.case_id,
            self.scenario_id,
        )


@dataclass(frozen=True)
class TrustedArtifactFact:
    """Hash-only artifact fact produced by a trusted A1 extractor."""

    binding: EvidenceBinding
    artifact_id: str
    modality: str
    producer_tool: str
    reference_id: str
    content_hash: str
    collection_status: str = "complete"

    def __post_init__(self) -> None:
        if not isinstance(self.binding, EvidenceBinding):
            raise TrustedEvidenceError(
                "invalid_artifact_binding", "artifact binding must be an EvidenceBinding"
            )
        _validate_opaque_identifier(self.artifact_id, "artifact_id")
        _validate_opaque_reference(self.reference_id)
        _validate_tool_name(self.producer_tool, "producer_tool")
        _validate_modality(self.modality)
        _validate_hash(self.content_hash, "content_hash")
        if self.collection_status not in COLLECTION_STATUSES:
            raise TrustedEvidenceError(
                "invalid_collection_status",
                f"unsupported collection_status: {self.collection_status!r}",
            )


@dataclass(frozen=True)
class TrustedEvidenceRequest:
    """One hash-only case request for the trusted evidence producer."""

    binding: EvidenceBinding
    created_at: str
    source_schema_version: str
    source_payload_hash: str
    required_modalities: tuple[str, ...]
    artifacts: tuple[TrustedArtifactFact, ...] = field(default_factory=tuple)
    tool_sequence: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.binding, EvidenceBinding):
            raise TrustedEvidenceError(
                "invalid_request_binding", "request binding must be an EvidenceBinding"
            )
        _canonical_timestamp(self.created_at)
        if not isinstance(self.source_schema_version, str) or not _SCHEMA_VERSION_RE.fullmatch(
            self.source_schema_version
        ):
            raise TrustedEvidenceError(
                "invalid_source_schema_version",
                "source_schema_version must be an opaque version identifier",
            )
        _validate_hash(self.source_payload_hash, "source_payload_hash")
        _validate_modalities(self.required_modalities, "required_modalities", require_nonempty=True)
        if not isinstance(self.artifacts, tuple):
            raise TrustedEvidenceError("invalid_artifacts", "artifacts must be a tuple")
        if not isinstance(self.tool_sequence, tuple):
            raise TrustedEvidenceError("invalid_tool_sequence", "tool_sequence must be a tuple")
        for index, tool in enumerate(self.tool_sequence):
            _validate_tool_name(tool, f"tool_sequence[{index}]")

        artifact_ids: set[str] = set()
        available_tools = set(self.tool_sequence)
        for index, artifact in enumerate(self.artifacts):
            if not isinstance(artifact, TrustedArtifactFact):
                raise TrustedEvidenceError(
                    "invalid_artifact", f"artifacts[{index}] must be a TrustedArtifactFact"
                )
            if artifact.binding != self.binding:
                raise TrustedEvidenceError(
                    "artifact_scope_mismatch",
                    f"artifacts[{index}] complete evidence binding does not match request",
                )
            if artifact.artifact_id in artifact_ids:
                raise TrustedEvidenceError(
                    "duplicate_artifact_id", f"duplicate artifact_id: {artifact.artifact_id}"
                )
            artifact_ids.add(artifact.artifact_id)
            if artifact.producer_tool not in available_tools:
                raise TrustedEvidenceError(
                    "producer_tool_missing_from_sequence",
                    f"artifact producer_tool is absent from tool_sequence: {artifact.producer_tool}",
                )


class TrustedEvidenceProducer:
    """Build and independently validate bounded A2-compatible snapshots."""

    def __init__(
        self,
        *,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
        max_artifacts_per_snapshot: int = DEFAULT_MAX_ARTIFACTS_PER_SNAPSHOT,
        max_tool_calls_per_snapshot: int = DEFAULT_MAX_TOOL_CALLS_PER_SNAPSHOT,
    ) -> None:
        self.max_batch_size = _validate_positive_limit(max_batch_size, "max_batch_size")
        self.max_artifacts_per_snapshot = _validate_positive_limit(
            max_artifacts_per_snapshot, "max_artifacts_per_snapshot"
        )
        self.max_tool_calls_per_snapshot = _validate_positive_limit(
            max_tool_calls_per_snapshot, "max_tool_calls_per_snapshot"
        )

    def produce(self, request: TrustedEvidenceRequest) -> dict[str, Any]:
        if not isinstance(request, TrustedEvidenceRequest):
            raise TrustedEvidenceError(
                "invalid_request", "request must be a TrustedEvidenceRequest"
            )
        if len(request.artifacts) > self.max_artifacts_per_snapshot:
            raise TrustedEvidenceError(
                "artifact_limit_exceeded",
                f"artifact count exceeds max_artifacts_per_snapshot={self.max_artifacts_per_snapshot}",
            )
        if len(request.tool_sequence) > self.max_tool_calls_per_snapshot:
            raise TrustedEvidenceError(
                "tool_call_limit_exceeded",
                f"tool call count exceeds max_tool_calls_per_snapshot={self.max_tool_calls_per_snapshot}",
            )

        artifacts = [
            _public_artifact_descriptor(item)
            for item in sorted(
                request.artifacts,
                key=lambda item: (
                    item.modality,
                    item.artifact_id,
                    item.producer_tool,
                    item.content_hash,
                ),
            )
        ]
        required = sorted(request.required_modalities)
        observed = sorted(
            {
                item["modality"]
                for item in artifacts
                if item["collection_status"] in {"complete", "partial"}
            }
        )
        missing = sorted(set(required) - set(observed))
        completeness = _snapshot_completeness(required, observed, artifacts)
        created_at = _canonical_timestamp(request.created_at)

        snapshot: dict[str, Any] = {
            "schema_version": EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
            **request.binding.as_dict(),
            "created_at": created_at,
            "source_schema_version": request.source_schema_version,
            "source_payload_hash": request.source_payload_hash,
            "required_modalities": required,
            "observed_modalities": observed,
            "completeness": completeness,
            "missing_modalities": missing,
            "tool_call_count": len(request.tool_sequence),
            "tool_sequence": list(request.tool_sequence),
            "artifacts": artifacts,
            "extractor_provenance": [
                {
                    "extractor_id": EXTRACTOR_ID,
                    "extractor_version": EXTRACTOR_VERSION,
                    "input_hash": request.source_payload_hash,
                    "status": completeness,
                }
            ],
            "security": dict(_SECURITY),
        }
        snapshot["snapshot_id"] = canonical_hash(snapshot)
        snapshot["snapshot_hash"] = canonical_hash(snapshot)
        validate_evidence_snapshot(snapshot, expected_binding=request.binding)
        return snapshot

    def produce_batch(
        self,
        requests: Iterable[TrustedEvidenceRequest],
        *,
        expected_organization_id: str | None = None,
        expected_tenant_id: str | None = None,
        expected_workspace_id: str | None = None,
        expected_project_id: str | None = None,
        expected_environment_id: str | None = None,
    ) -> list[dict[str, Any]]:
        materialized = list(requests)
        if not materialized:
            raise TrustedEvidenceError("empty_batch", "evidence batch must not be empty")
        if len(materialized) > self.max_batch_size:
            raise TrustedEvidenceError(
                "batch_limit_exceeded",
                f"evidence batch exceeds max_batch_size={self.max_batch_size}",
            )
        if expected_organization_id is not None:
            _validate_opaque_identifier(
                expected_organization_id, "expected_organization_id"
            )
        if expected_tenant_id is not None:
            _validate_opaque_identifier(expected_tenant_id, "expected_tenant_id")
        if expected_workspace_id is not None:
            _validate_opaque_identifier(expected_workspace_id, "expected_workspace_id")
        if expected_project_id is not None:
            _validate_opaque_identifier(expected_project_id, "expected_project_id")
        if expected_environment_id is not None:
            _validate_opaque_identifier(
                expected_environment_id, "expected_environment_id"
            )

        seen_bindings: set[tuple[str, str, str, str, str, str, str, str]] = set()
        snapshots: list[dict[str, Any]] = []
        for index, request in enumerate(materialized):
            if not isinstance(request, TrustedEvidenceRequest):
                raise TrustedEvidenceError(
                    "invalid_batch_request",
                    f"requests[{index}] must be a TrustedEvidenceRequest",
                )
            binding = request.binding
            if (
                expected_organization_id is not None
                and binding.organization_id != expected_organization_id
            ):
                raise TrustedEvidenceError(
                    "batch_organization_mismatch",
                    f"requests[{index}] organization does not match the batch organization",
                )
            if expected_tenant_id is not None and binding.tenant_id != expected_tenant_id:
                raise TrustedEvidenceError(
                    "batch_tenant_mismatch",
                    f"requests[{index}] tenant does not match the batch tenant",
                )
            if (
                expected_workspace_id is not None
                and binding.workspace_id != expected_workspace_id
            ):
                raise TrustedEvidenceError(
                    "batch_workspace_mismatch",
                    f"requests[{index}] workspace does not match the batch workspace",
                )
            if expected_project_id is not None and binding.project_id != expected_project_id:
                raise TrustedEvidenceError(
                    "batch_project_mismatch",
                    f"requests[{index}] project does not match the batch project",
                )
            if (
                expected_environment_id is not None
                and binding.environment_id != expected_environment_id
            ):
                raise TrustedEvidenceError(
                    "batch_environment_mismatch",
                    f"requests[{index}] environment does not match the batch environment",
                )
            if binding.key() in seen_bindings:
                raise TrustedEvidenceError(
                    "duplicate_case_binding",
                    f"duplicate complete evidence binding at requests[{index}]",
                )
            seen_bindings.add(binding.key())
            snapshots.append(self.produce(request))
        return snapshots


def canonical_json(value: Any) -> str:
    """Return the A2-compatible canonical JSON representation."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TrustedEvidenceError(
            "non_canonical_value", "value is not canonical JSON data"
        ) from exc


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_evidence_snapshot(
    snapshot: Mapping[str, Any],
    *,
    expected_binding: EvidenceBinding | None = None,
) -> None:
    """Fail closed if a snapshot violates the A1 or A2 public contract."""

    if not isinstance(snapshot, Mapping):
        raise TrustedEvidenceError("invalid_snapshot", "snapshot must be an object")
    keys = frozenset(snapshot)
    if keys != _SNAPSHOT_KEYS:
        missing = sorted(_SNAPSHOT_KEYS - keys)
        extra = sorted(keys - _SNAPSHOT_KEYS)
        raise TrustedEvidenceError(
            "snapshot_shape_mismatch",
            f"snapshot keys do not match contract; missing={missing}, extra={extra}",
        )
    if snapshot["schema_version"] != EVIDENCE_SNAPSHOT_SCHEMA_VERSION:
        raise TrustedEvidenceError("schema_version_mismatch", "unsupported snapshot schema")

    binding = EvidenceBinding(
        organization_id=_require_string(snapshot["organization_id"], "organization_id"),
        tenant_id=_require_string(snapshot["tenant_id"], "tenant_id"),
        workspace_id=_require_string(snapshot["workspace_id"], "workspace_id"),
        project_id=_require_string(snapshot["project_id"], "project_id"),
        environment_id=_require_string(snapshot["environment_id"], "environment_id"),
        run_id=_require_string(snapshot["run_id"], "run_id"),
        case_id=_require_string(snapshot["case_id"], "case_id"),
        scenario_id=_require_string(snapshot["scenario_id"], "scenario_id"),
    )
    if expected_binding is not None and binding != expected_binding:
        raise TrustedEvidenceError(
            "snapshot_scope_mismatch",
            "snapshot complete evidence binding does not match expected scope",
        )
    if snapshot["created_at"] != _canonical_timestamp(
        _require_string(snapshot["created_at"], "created_at")
    ):
        raise TrustedEvidenceError(
            "non_canonical_created_at", "created_at must be canonical UTC with a Z suffix"
        )
    source_schema_version = _require_string(
        snapshot["source_schema_version"], "source_schema_version"
    )
    if not _SCHEMA_VERSION_RE.fullmatch(source_schema_version):
        raise TrustedEvidenceError(
            "invalid_source_schema_version", "source_schema_version is invalid"
        )
    _validate_hash(snapshot["source_payload_hash"], "source_payload_hash")
    _validate_hash(snapshot["snapshot_id"], "snapshot_id")
    _validate_hash(snapshot["snapshot_hash"], "snapshot_hash")

    required = _validated_modality_list(
        snapshot["required_modalities"], "required_modalities", require_nonempty=True
    )
    observed = _validated_modality_list(
        snapshot["observed_modalities"], "observed_modalities"
    )
    missing = _validated_modality_list(snapshot["missing_modalities"], "missing_modalities")
    if missing != sorted(set(required) - set(observed)):
        raise TrustedEvidenceError(
            "missing_modalities_mismatch", "missing_modalities does not match required evidence"
        )
    completeness = snapshot["completeness"]
    if completeness not in COMPLETENESS_STATUSES:
        raise TrustedEvidenceError("invalid_completeness", "snapshot completeness is invalid")

    tool_sequence = snapshot["tool_sequence"]
    if not isinstance(tool_sequence, list):
        raise TrustedEvidenceError("invalid_tool_sequence", "tool_sequence must be an array")
    for index, tool in enumerate(tool_sequence):
        _validate_tool_name(tool, f"tool_sequence[{index}]")
    tool_call_count = snapshot["tool_call_count"]
    if isinstance(tool_call_count, bool) or not isinstance(tool_call_count, int):
        raise TrustedEvidenceError("invalid_tool_call_count", "tool_call_count must be an integer")
    if tool_call_count < 0 or tool_call_count != len(tool_sequence):
        raise TrustedEvidenceError(
            "tool_call_count_mismatch", "tool_call_count does not match tool_sequence"
        )

    artifacts = snapshot["artifacts"]
    if not isinstance(artifacts, list):
        raise TrustedEvidenceError("invalid_artifacts", "artifacts must be an array")
    artifact_ids: set[str] = set()
    expected_artifact_order: list[tuple[str, str, str, str]] = []
    artifact_observed: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, Mapping) or frozenset(artifact) != _ARTIFACT_KEYS:
            raise TrustedEvidenceError(
                "artifact_shape_mismatch", f"artifacts[{index}] does not match contract"
            )
        artifact_id = _require_string(artifact["artifact_id"], f"artifacts[{index}].artifact_id")
        _validate_opaque_identifier(artifact_id, f"artifacts[{index}].artifact_id")
        if artifact_id in artifact_ids:
            raise TrustedEvidenceError(
                "duplicate_artifact_id", f"duplicate artifact_id: {artifact_id}"
            )
        artifact_ids.add(artifact_id)
        modality = _require_string(artifact["modality"], f"artifacts[{index}].modality")
        _validate_modality(modality)
        producer_tool = _require_string(
            artifact["producer_tool"], f"artifacts[{index}].producer_tool"
        )
        _validate_tool_name(producer_tool, f"artifacts[{index}].producer_tool")
        if producer_tool not in tool_sequence:
            raise TrustedEvidenceError(
                "producer_tool_missing_from_sequence",
                f"artifacts[{index}] producer_tool is absent from tool_sequence",
            )
        _validate_hash(artifact["reference_hash"], f"artifacts[{index}].reference_hash")
        content_hash = _require_string(
            artifact["content_hash"], f"artifacts[{index}].content_hash"
        )
        _validate_hash(content_hash, f"artifacts[{index}].content_hash")
        if artifact["content_included"] is not False:
            raise TrustedEvidenceError(
                "artifact_content_included", "artifact content must never enter a public snapshot"
            )
        status = artifact["collection_status"]
        if status not in COLLECTION_STATUSES:
            raise TrustedEvidenceError(
                "invalid_collection_status", f"artifacts[{index}] collection_status is invalid"
            )
        if status in {"complete", "partial"}:
            artifact_observed.add(modality)
        expected_artifact_order.append((modality, artifact_id, producer_tool, content_hash))
    if expected_artifact_order != sorted(expected_artifact_order):
        raise TrustedEvidenceError(
            "non_canonical_artifact_order", "artifacts must use canonical deterministic ordering"
        )
    if observed != sorted(artifact_observed):
        raise TrustedEvidenceError(
            "observed_modalities_mismatch",
            "observed_modalities does not match hash-only artifact facts",
        )
    expected_completeness = _snapshot_completeness(required, observed, artifacts)
    if completeness != expected_completeness:
        raise TrustedEvidenceError(
            "completeness_mismatch",
            f"completeness must be {expected_completeness!r} for the supplied facts",
        )

    provenance = snapshot["extractor_provenance"]
    if not isinstance(provenance, list) or len(provenance) != 1:
        raise TrustedEvidenceError(
            "invalid_extractor_provenance", "exactly one stable extractor record is required"
        )
    extractor = provenance[0]
    if not isinstance(extractor, Mapping) or frozenset(extractor) != _PROVENANCE_KEYS:
        raise TrustedEvidenceError(
            "invalid_extractor_provenance", "extractor provenance does not match contract"
        )
    expected_provenance = {
        "extractor_id": EXTRACTOR_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "input_hash": snapshot["source_payload_hash"],
        "status": completeness,
    }
    if dict(extractor) != expected_provenance:
        raise TrustedEvidenceError(
            "extractor_provenance_mismatch", "extractor provenance is not stable"
        )
    if snapshot["security"] != _SECURITY:
        raise TrustedEvidenceError(
            "public_safety_mismatch", "snapshot public-safety flags must fail closed"
        )

    unsigned = {
        key: value
        for key, value in snapshot.items()
        if key not in {"snapshot_id", "snapshot_hash"}
    }
    expected_snapshot_id = canonical_hash(unsigned)
    if snapshot["snapshot_id"] != expected_snapshot_id:
        raise TrustedEvidenceError("snapshot_id_mismatch", "snapshot_id hash mismatch")
    expected_snapshot_hash = canonical_hash({**unsigned, "snapshot_id": expected_snapshot_id})
    if snapshot["snapshot_hash"] != expected_snapshot_hash:
        raise TrustedEvidenceError("snapshot_hash_mismatch", "snapshot_hash mismatch")


def validate_evidence_batch(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    expected_organization_id: str | None = None,
    expected_tenant_id: str,
    expected_workspace_id: str | None = None,
    expected_project_id: str | None = None,
    expected_environment_id: str | None = None,
    max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
) -> None:
    if not isinstance(snapshots, Sequence) or isinstance(snapshots, (str, bytes)):
        raise TrustedEvidenceError("invalid_batch", "snapshots must be a sequence")
    limit = _validate_positive_limit(max_batch_size, "max_batch_size")
    if not snapshots:
        raise TrustedEvidenceError("empty_batch", "snapshot batch must not be empty")
    if len(snapshots) > limit:
        raise TrustedEvidenceError(
            "batch_limit_exceeded", f"snapshot batch exceeds max_batch_size={limit}"
        )
    if expected_organization_id is not None:
        _validate_opaque_identifier(
            expected_organization_id, "expected_organization_id"
        )
    _validate_opaque_identifier(expected_tenant_id, "expected_tenant_id")
    if expected_workspace_id is not None:
        _validate_opaque_identifier(expected_workspace_id, "expected_workspace_id")
    if expected_project_id is not None:
        _validate_opaque_identifier(expected_project_id, "expected_project_id")
    if expected_environment_id is not None:
        _validate_opaque_identifier(
            expected_environment_id, "expected_environment_id"
        )
    seen_bindings: set[tuple[str, str, str, str, str, str, str, str]] = set()
    for index, snapshot in enumerate(snapshots):
        binding = EvidenceBinding(
            organization_id=_mapping_string(snapshot, "organization_id", index),
            tenant_id=_mapping_string(snapshot, "tenant_id", index),
            workspace_id=_mapping_string(snapshot, "workspace_id", index),
            project_id=_mapping_string(snapshot, "project_id", index),
            environment_id=_mapping_string(snapshot, "environment_id", index),
            run_id=_mapping_string(snapshot, "run_id", index),
            case_id=_mapping_string(snapshot, "case_id", index),
            scenario_id=_mapping_string(snapshot, "scenario_id", index),
        )
        if (
            expected_organization_id is not None
            and binding.organization_id != expected_organization_id
        ):
            raise TrustedEvidenceError(
                "batch_organization_mismatch",
                f"snapshots[{index}] has the wrong organization",
            )
        if binding.tenant_id != expected_tenant_id:
            raise TrustedEvidenceError(
                "batch_tenant_mismatch", f"snapshots[{index}] has the wrong tenant"
            )
        if (
            expected_workspace_id is not None
            and binding.workspace_id != expected_workspace_id
        ):
            raise TrustedEvidenceError(
                "batch_workspace_mismatch",
                f"snapshots[{index}] has the wrong workspace",
            )
        if expected_project_id is not None and binding.project_id != expected_project_id:
            raise TrustedEvidenceError(
                "batch_project_mismatch", f"snapshots[{index}] has the wrong project"
            )
        if (
            expected_environment_id is not None
            and binding.environment_id != expected_environment_id
        ):
            raise TrustedEvidenceError(
                "batch_environment_mismatch",
                f"snapshots[{index}] has the wrong environment",
            )
        if binding.key() in seen_bindings:
            raise TrustedEvidenceError(
                "duplicate_case_binding", f"duplicate binding at snapshots[{index}]"
            )
        seen_bindings.add(binding.key())
        validate_evidence_snapshot(snapshot, expected_binding=binding)


def _public_artifact_descriptor(fact: TrustedArtifactFact) -> dict[str, Any]:
    reference_hash = canonical_hash(
        {
            "schema_version": REFERENCE_HASH_SCHEMA_VERSION,
            "binding": fact.binding.as_dict(),
            "artifact_id": fact.artifact_id,
            "modality": fact.modality,
            "producer_tool": fact.producer_tool,
            "reference_id": fact.reference_id,
        }
    )
    return {
        "artifact_id": fact.artifact_id,
        "modality": fact.modality,
        "producer_tool": fact.producer_tool,
        "reference_hash": reference_hash,
        "content_hash": fact.content_hash,
        "content_included": False,
        "collection_status": fact.collection_status,
    }


def _snapshot_completeness(
    required: Sequence[str],
    observed: Sequence[str],
    artifacts: Sequence[Mapping[str, Any]],
) -> str:
    statuses = {str(item.get("collection_status")) for item in artifacts}
    if "invalid" in statuses:
        return "invalid"
    missing = set(required) - set(observed)
    if missing and not (set(required) & set(observed)):
        return "evidence_missing"
    if missing or statuses & {"partial", "evidence_missing"}:
        return "partial"
    return "complete"


def _canonical_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise TrustedEvidenceError("invalid_created_at", "created_at must be an ISO timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise TrustedEvidenceError("invalid_created_at", "created_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrustedEvidenceError("invalid_created_at", "created_at must include a timezone")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond:
        formatted = parsed.isoformat(timespec="microseconds")
    else:
        formatted = parsed.isoformat(timespec="seconds")
    return formatted.replace("+00:00", "Z")


def _validated_modality_list(
    value: Any, name: str, *, require_nonempty: bool = False
) -> list[str]:
    if not isinstance(value, list):
        raise TrustedEvidenceError("invalid_modalities", f"{name} must be an array")
    result = [_require_string(item, f"{name}[{index}]") for index, item in enumerate(value)]
    _validate_modalities(tuple(result), name, require_nonempty=require_nonempty)
    if result != sorted(result):
        raise TrustedEvidenceError(
            "non_canonical_modalities", f"{name} must use canonical sorted ordering"
        )
    return result


def _validate_modalities(
    value: tuple[str, ...], name: str, *, require_nonempty: bool = False
) -> None:
    if not isinstance(value, tuple):
        raise TrustedEvidenceError("invalid_modalities", f"{name} must be a tuple")
    if require_nonempty and not value:
        raise TrustedEvidenceError("missing_modalities", f"{name} must not be empty")
    if len(value) != len(set(value)):
        raise TrustedEvidenceError("duplicate_modality", f"{name} contains a duplicate modality")
    for modality in value:
        _validate_modality(modality)


def _validate_modality(value: Any) -> None:
    if value not in MODALITIES:
        raise TrustedEvidenceError("invalid_modality", f"unsupported modality: {value!r}")


def _validate_hash(value: Any, name: str) -> None:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise TrustedEvidenceError("malformed_hash", f"{name} must be sha256:<64 lowercase hex>")


def _validate_opaque_identifier(value: Any, name: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise TrustedEvidenceError(
            "invalid_identifier", f"{name} must be a non-path opaque identifier"
        )
    _reject_public_identifier_hazards(value, name)


def _validate_opaque_reference(value: Any) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise TrustedEvidenceError(
            "unsafe_reference", "reference_id must be a non-path opaque identifier"
        )
    _reject_public_identifier_hazards(value, "reference_id")


def _validate_tool_name(value: Any, name: str) -> None:
    if not isinstance(value, str) or not _TOOL_RE.fullmatch(value):
        raise TrustedEvidenceError("invalid_tool_name", f"{name} is invalid")
    _reject_traversal(value, name)


def _reject_traversal(value: str, name: str) -> None:
    lowered = value.lower()
    if (
        ".." in value
        or "/" in value
        or "\\" in value
        or "://" in lowered
        or _ENCODED_TRAVERSAL_RE.search(value)
        or "private_refs" in lowered
    ):
        raise TrustedEvidenceError(
            "path_or_private_reference_rejected", f"{name} must not contain a path or private reference"
        )


def _reject_public_identifier_hazards(value: str, name: str) -> None:
    _reject_traversal(value, name)
    lowered = value.lower()
    if (
        "@" in value
        or lowered.startswith(("mailto:", "data:", "file:", "urn:"))
        or _SECRET_SHAPED_IDENTIFIER_RE.search(value)
    ):
        raise TrustedEvidenceError(
            "pii_or_secret_identifier_rejected",
            f"{name} must not contain PII, a URI, or a secret-shaped value",
        )


def _validate_positive_limit(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TrustedEvidenceError("invalid_limit", f"{name} must be a positive integer")
    return value


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise TrustedEvidenceError("invalid_string", f"{name} must be a string")
    return value


def _mapping_string(snapshot: Mapping[str, Any], name: str, index: int) -> str:
    if not isinstance(snapshot, Mapping):
        raise TrustedEvidenceError("invalid_snapshot", f"snapshots[{index}] must be an object")
    return _require_string(snapshot.get(name), f"snapshots[{index}].{name}")


__all__ = [
    "COLLECTION_STATUSES",
    "DEFAULT_MAX_ARTIFACTS_PER_SNAPSHOT",
    "DEFAULT_MAX_BATCH_SIZE",
    "DEFAULT_MAX_TOOL_CALLS_PER_SNAPSHOT",
    "EVIDENCE_SNAPSHOT_SCHEMA_VERSION",
    "EXTRACTOR_ID",
    "EXTRACTOR_VERSION",
    "EvidenceBinding",
    "MODALITIES",
    "TrustedArtifactFact",
    "TrustedEvidenceError",
    "TrustedEvidenceProducer",
    "TrustedEvidenceRequest",
    "canonical_hash",
    "canonical_json",
    "validate_evidence_batch",
    "validate_evidence_snapshot",
]
