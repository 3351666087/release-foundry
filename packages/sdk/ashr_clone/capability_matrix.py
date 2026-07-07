"""Public-safe commercial capability matrix for A1 artifacts.

This module intentionally consumes only public-safe summaries: the public API
evidence index, the frontend mirror index, local SDK symbol metadata, and tests.
It never opens private evidence records or reads environment keys.
"""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .api_client import ASHR_API_FIELD_MAP_VERSION, AshrApiClient, redact_sensitive

JsonDict = dict[str, Any]
CAPABILITY_MATRIX_SCHEMA_VERSION = "ashr.clone.capability_matrix.v1"

_READ_PREFIXES = ("get_", "list_", "poll_", "validate_", "plan_")
_MUTATING_PREFIXES = ("create_", "update_", "delete_", "revoke_", "evaluate_")
_LOCAL_RUNTIME_CAPABILITIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("agent_adapter", "local_runtime", ("AgentAdapter", "coerce_agent_input", "to_a2_judge_run")),
    ("api_client", "local_runtime", ("AshrApiClient", "dry_run", "transport")),
    ("api_preflight", "local_runtime", ("enforce_create_request_preflight", "summarize_generation_request")),
    ("capability_matrix", "local_runtime", ("build_capability_matrix", "write_capability_matrix")),
    ("dataset_adapter", "local_runtime", ("dataset_source_to_cases", "api_record_to_cases")),
    ("evidence_index", "local_runtime", ("build_private_evidence_index", "validate_public_evidence_index")),
    ("output_policy_guard", "local_runtime", ("output_policy", "private_output_required", "full_record_stdout_blocked")),
    ("response_field_map", "local_runtime", ("build_response_field_map", "render_response_field_map_markdown")),
    ("trace_fixture", "local_runtime", ("TraceRecorder", "build_run_fixture", "build_vm_stream")),
)
_SECRET_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"ashr_live_[A-Za-z0-9_\-]+"),
)


@dataclass(frozen=True, slots=True)
class CapabilityMatrixInputs:
    public_evidence_index_path: Path
    frontend_mirror_index_path: Path
    tests_root: Path | None = None
    source_label: str = "a1-round15-commercial-capability-matrix"


def load_public_json(path: str | Path) -> JsonDict:
    """Load a public summary JSON file.

    Guardrails reject paths that point at private evidence roots. The matrix only
    needs the already-sanitized indexes committed under docs/a1.
    """

    resolved = Path(path)
    normalized = resolved.as_posix().lower()
    if "private_refs" in normalized or "secrets" in normalized or normalized.endswith(".env"):
        raise ValueError(f"refusing to load non-public capability-matrix input: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object JSON input: {resolved}")
    return payload


def build_capability_matrix(inputs: CapabilityMatrixInputs | Mapping[str, Any]) -> JsonDict:
    opts = _coerce_inputs(inputs)
    evidence_index = load_public_json(opts.public_evidence_index_path)
    frontend_index = load_public_json(opts.frontend_mirror_index_path)
    tests_text = _read_public_tests(opts.tests_root) if opts.tests_root is not None else ""

    evidence_by_function = _summarize_public_evidence(evidence_index)
    frontend_functions = sorted(str(name) for name in frontend_index.get("api_functions", []) if isinstance(name, str))
    local_api_functions = _local_api_functions()
    capabilities: dict[str, JsonDict] = {}

    for function_name in sorted(set(evidence_by_function) | set(frontend_functions) | set(local_api_functions)):
        evidence = evidence_by_function.get(function_name, {})
        mutating = _is_mutating(function_name)
        real_read_verified = bool((not mutating) and evidence.get("real_ok_count", 0) > 0)
        mutating_planned_or_quota_blocked = bool(
            mutating
            and (evidence.get("planned_count", 0) > 0 or evidence.get("quota_block_count", 0) > 0 or evidence.get("real_error_count", 0) > 0)
        )
        frontend_mirrored = function_name in frontend_functions
        local_runtime = function_name in local_api_functions
        capabilities[function_name] = _capability_entry(
            name=function_name,
            category="api_function",
            local_runtime=local_runtime,
            local_only=False,
            real_read_verified=real_read_verified,
            mutating_planned_or_quota_blocked=mutating_planned_or_quota_blocked,
            frontend_mirrored=frontend_mirrored,
            test_covered=_token_covered(tests_text, function_name),
            evidence=evidence,
            source_notes=_source_notes(local_runtime, real_read_verified, mutating_planned_or_quota_blocked, frontend_mirrored),
        )

    for name, category, coverage_tokens in _LOCAL_RUNTIME_CAPABILITIES:
        capabilities[name] = _capability_entry(
            name=name,
            category=category,
            local_runtime=True,
            local_only=True,
            real_read_verified=False,
            mutating_planned_or_quota_blocked=False,
            frontend_mirrored=False,
            test_covered=any(_token_covered(tests_text, token) for token in (name, *coverage_tokens)),
            evidence={},
            source_notes=["local SDK/runtime implementation"],
        )

    entries = [capabilities[name] for name in sorted(capabilities)]
    matrix = {
            "schema_version": CAPABILITY_MATRIX_SCHEMA_VERSION,
            "label": opts.source_label,
            "field_map_version": ASHR_API_FIELD_MAP_VERSION,
            "public_safe": True,
            "secret_policy": {
                "private_evidence_read": False,
                "tokens_included": False,
                "raw_private_payloads_included": False,
                "input_sources": [
                    "public_evidence_index",
                    "frontend_mirror_index",
                    "local_runtime_symbols",
                    "tests_a1_static_coverage",
                ],
            },
            "source_indexes": {
                "public_evidence": {
                    "schema_version": evidence_index.get("schema_version"),
                    "label": evidence_index.get("label"),
                    "total_records": evidence_index.get("total_records", 0),
                    "function_count": len(evidence_by_function),
                    "quota_block_count": evidence_index.get("quota_block_count", 0),
                },
                "frontend_mirror": {
                    "schema_version": frontend_index.get("schema_version"),
                    "raw_files_committed": frontend_index.get("raw_files_committed"),
                    "public_safe_summary": frontend_index.get("public_safe_summary"),
                    "api_function_count": len(frontend_functions),
                    "api_entrypoints": sorted(str(item) for item in frontend_index.get("api_entrypoints", []) if isinstance(item, str)),
                },
            },
            "summary": _summary(entries),
            "capabilities": entries,
        }
    validate_capability_matrix(matrix)
    return matrix


def _redact_capability_matrix(value: Mapping[str, Any]) -> JsonDict:
    redacted = redact_sensitive(dict(value))
    policy = value.get("secret_policy")
    if isinstance(policy, Mapping):
        redacted["secret_policy"] = {
            key: redact_sensitive(item)
            for key, item in policy.items()
            if key in {"private_evidence_read", "tokens_included", "raw_private_payloads_included", "input_sources"}
        }
    return redacted


def write_capability_matrix(path: str | Path, matrix: Mapping[str, Any]) -> Path:
    validate_capability_matrix(matrix)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(matrix), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def validate_capability_matrix(matrix: Mapping[str, Any]) -> list[JsonDict]:
    issues: list[JsonDict] = []
    if matrix.get("schema_version") != CAPABILITY_MATRIX_SCHEMA_VERSION:
        issues.append({"severity": "error", "kind": "bad_schema_version"})
    if matrix.get("public_safe") is not True:
        issues.append({"severity": "error", "kind": "not_marked_public_safe"})
    text = json.dumps(matrix, sort_keys=True)
    if "private_refs" in text:
        issues.append({"severity": "error", "kind": "private_ref_path_leaked"})
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            issues.append({"severity": "error", "kind": "secret_like_value_leaked", "pattern": pattern.pattern})
    names: set[str] = set()
    for offset, entry in enumerate(matrix.get("capabilities", [])):
        if not isinstance(entry, Mapping):
            issues.append({"severity": "error", "kind": "bad_capability_entry", "index": offset})
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            issues.append({"severity": "error", "kind": "missing_capability_name", "index": offset})
        elif name in names:
            issues.append({"severity": "error", "kind": "duplicate_capability_name", "name": name})
        else:
            names.add(name)
        for key in ("local_only", "real_read_verified", "mutating_planned_or_quota_blocked", "frontend_mirrored", "test_covered"):
            if not isinstance(entry.get(key), bool):
                issues.append({"severity": "error", "kind": "non_boolean_axis", "name": name, "field": key})
    return issues


def assert_capability_matrix_safe(matrix: Mapping[str, Any]) -> None:
    issues = validate_capability_matrix(matrix)
    blocking = [issue for issue in issues if issue.get("severity") == "error"]
    if blocking:
        raise ValueError(f"capability matrix has {len(blocking)} public-safety/schema issue(s): {blocking[:3]}")


def _coerce_inputs(inputs: CapabilityMatrixInputs | Mapping[str, Any]) -> CapabilityMatrixInputs:
    if isinstance(inputs, CapabilityMatrixInputs):
        return inputs
    return CapabilityMatrixInputs(
        public_evidence_index_path=Path(inputs["public_evidence_index_path"]),
        frontend_mirror_index_path=Path(inputs["frontend_mirror_index_path"]),
        tests_root=Path(inputs["tests_root"]) if inputs.get("tests_root") is not None else None,
        source_label=str(inputs.get("source_label") or "a1-round15-commercial-capability-matrix"),
    )


def _local_api_functions() -> set[str]:
    excluded = {"call", "from_env", "health_check", "init", "plan"}
    functions: set[str] = {"init", "keep_alive"}
    for name, member in inspect.getmembers(AshrApiClient, predicate=inspect.isfunction):
        if name.startswith("_") or name in excluded:
            continue
        functions.add("keep_alive" if name == "health_check" else name)
    return functions


def _summarize_public_evidence(index: Mapping[str, Any]) -> dict[str, JsonDict]:
    by_function: dict[str, JsonDict] = {}
    records = index.get("records") if isinstance(index.get("records"), list) else []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        function = record.get("function")
        if not isinstance(function, str) or not function:
            continue
        item = by_function.setdefault(
            function,
            {
                "records": 0,
                "planned_count": 0,
                "real_ok_count": 0,
                "real_error_count": 0,
                "quota_block_count": 0,
                "status_counts": {},
                "status_codes": [],
                "response_keys": [],
                "error_keys": [],
            },
        )
        item["records"] += 1
        status = str(record.get("status")) if record.get("status") is not None else "unknown"
        item["status_counts"][status] = item["status_counts"].get(status, 0) + 1
        if record.get("dry_run") is True or status == "planned":
            item["planned_count"] += 1
        elif status == "ok":
            item["real_ok_count"] += 1
        elif status == "error":
            item["real_error_count"] += 1
        quota = record.get("quota") if isinstance(record.get("quota"), Mapping) else {}
        if quota.get("blocked") is True:
            item["quota_block_count"] += 1
        status_code = record.get("status_code")
        if isinstance(status_code, int) and status_code not in item["status_codes"]:
            item["status_codes"].append(status_code)
        for source_key in ("response_keys", "error_keys"):
            merged = set(item[source_key])
            merged.update(str(value) for value in record.get(source_key, []) if isinstance(value, str))
            item[source_key] = sorted(merged)
    for item in by_function.values():
        item["status_counts"] = dict(sorted(item["status_counts"].items()))
        item["status_codes"] = sorted(item["status_codes"])
    return dict(sorted(by_function.items()))


def _read_public_tests(tests_root: Path) -> str:
    if not tests_root.exists():
        return ""
    chunks: list[str] = []
    for path in sorted(tests_root.glob("test_*.py")):
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _capability_entry(
    *,
    name: str,
    category: str,
    local_runtime: bool,
    local_only: bool,
    real_read_verified: bool,
    mutating_planned_or_quota_blocked: bool,
    frontend_mirrored: bool,
    test_covered: bool,
    evidence: Mapping[str, Any],
    source_notes: Iterable[str],
) -> JsonDict:
    return {
        "name": name,
        "category": category,
        "local_runtime": bool(local_runtime),
        "local_only": bool(local_only),
        "real_read_verified": bool(real_read_verified),
        "mutating_planned_or_quota_blocked": bool(mutating_planned_or_quota_blocked),
        "frontend_mirrored": bool(frontend_mirrored),
        "test_covered": bool(test_covered),
        "evidence": dict(evidence),
        "source_notes": sorted(set(source_notes)),
    }


def _source_notes(local_runtime: bool, real_read_verified: bool, mutating_planned_or_quota_blocked: bool, frontend_mirrored: bool) -> list[str]:
    notes: list[str] = []
    if local_runtime:
        notes.append("local SDK method present")
    if real_read_verified:
        notes.append("real read evidence has public-safe ok record")
    if mutating_planned_or_quota_blocked:
        notes.append("mutating capability observed as dry-run plan, error, or quota block")
    if frontend_mirrored:
        notes.append("frontend mirror names this API function")
    return notes


def _summary(entries: list[Mapping[str, Any]]) -> JsonDict:
    axis_names = ("local_only", "real_read_verified", "mutating_planned_or_quota_blocked", "frontend_mirrored", "test_covered")
    return {
        "total_capabilities": len(entries),
        "axis_counts": {axis: sum(1 for entry in entries if entry.get(axis) is True) for axis in axis_names},
        "categories": _count_values(entry.get("category") for entry in entries),
    }


def _count_values(values: Iterable[Any]) -> JsonDict:
    counts: dict[str, int] = {}
    for value in values:
        if isinstance(value, str):
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _is_mutating(function_name: str) -> bool:
    return function_name.startswith(_MUTATING_PREFIXES) or function_name.startswith("billing_create_")


def _token_covered(text: str, token: str) -> bool:
    if not text or not token:
        return False
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text) is not None


def load_json(path: str | Path) -> JsonDict:
    """Compatibility alias for public-safe JSON loading."""

    return load_public_json(path)


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def summarize_legacy_evidence(index: Mapping[str, Any]) -> JsonDict:
    records = index.get("records") if isinstance(index.get("records"), list) else []
    missing_by_function: dict[str, int] = {}
    present = 0
    malformed = 0
    real_missing = 0
    for record in records:
        if not isinstance(record, Mapping):
            continue
        function = str(record.get("function") or "unknown")
        policy = record.get("output_policy")
        if isinstance(policy, Mapping):
            present += 1
        elif policy is None:
            missing_by_function[function] = missing_by_function.get(function, 0) + 1
            if record.get("dry_run") is False:
                real_missing += 1
        else:
            malformed += 1
    counts = index.get("output_policy_counts") if isinstance(index.get("output_policy_counts"), Mapping) else {}
    unsafe = int(counts.get("unsafe_real_nonprivate_override", 0) or 0)
    return {
        "schema_version": "ashr.clone.legacy_evidence_summary.v1",
        "source_label": index.get("label"),
        "source_total_records": index.get("total_records", len(records)),
        "output_policy_present": present,
        "output_policy_missing": sum(missing_by_function.values()),
        "output_policy_malformed": malformed,
        "real_records_missing_output_policy": real_missing,
        "unsafe_real_nonprivate_override": unsafe,
        "missing_by_function": dict(sorted(missing_by_function.items())),
        "readiness_gate": {
            "public_index_safe": unsafe == 0 and malformed == 0,
            "legacy_policy_backfill_required": bool(missing_by_function),
            "blocking_reason": None if unsafe == 0 and malformed == 0 else "unsafe output policy evidence present",
        },
    }
