from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Mapping

from .api_client import ASHR_API_FIELD_MAP_VERSION, redact_sensitive, summarize_quota_error

JsonDict = dict[str, Any]
OUTPUT_POLICY_SCHEMA_VERSION = "ashr.clone.output_policy.v1"
_REAL_RECORD_CLASSES = {"real_readonly", "real_mutating", "quota_gate"}
EVIDENCE_INDEX_SCHEMA_VERSION = "ashr.clone.evidence_index.v1"
_PUBLIC_SECRET_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+(?=[A-Za-z0-9._\-]*(?:\d|[._\-]))[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"ashr_live_[A-Za-z0-9_\-]+"),
)
_PUBLIC_ARTIFACT_SECRET_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    *(("secret_like_text", pattern) for pattern in _PUBLIC_SECRET_PATTERNS),
    ("authorization_header", re.compile(r"\bAuthorization\s*[:=]\s*[^\s`'\"]+", re.IGNORECASE)),
    ("api_key_header", re.compile(r"\b(?:X-API-Key|x-api-key)\s*[:=]\s*[^\s`'\"]+", re.IGNORECASE)),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "raw_private_payload_included",
        re.compile(r"\b(?:raw_)?(?:private_)?(?:payloads?|requests?|responses?|headers?)_included\b\s*[:=]\s*(?:true|1|yes)\b", re.IGNORECASE),
    ),
)


@dataclass(slots=True)
class EvidenceIndexOptions:
    include_patterns: tuple[str, ...] = ("*.json",)
    max_files: int | None = None
    label: str = "a1-real-api"


class PublicEvidenceIndexError(ValueError):
    """Raised when a public-safe evidence index contains blocking safety issues."""

    def __init__(self, issues: list[JsonDict]):
        self.issues = issues
        super().__init__(f"public evidence index has {len(issues)} blocking issue(s)")


def build_private_evidence_index(paths: Iterable[str | Path], *, label: str = "a1-real-api", strict_public: bool = False) -> JsonDict:
    entries = [_summarize_record_path(Path(path)) for path in paths]
    entries = [entry for entry in entries if entry is not None]
    entries.sort(key=lambda item: str(item["path"]))
    index = _build_evidence_index(entries, label=label)
    if strict_public:
        assert_public_evidence_index_safe(index)
    return index


def merge_evidence_indices(existing_index: Mapping[str, Any] | None, fresh_index: Mapping[str, Any], *, label: str = "a1-real-api") -> JsonDict:
    entries_by_path: dict[str, JsonDict] = {}
    if isinstance(existing_index, Mapping):
        entries_by_path.update(_records_by_path(existing_index.get("records", [])))
    entries_by_path.update(_records_by_path(fresh_index.get("records", [])))
    entries = sorted(entries_by_path.values(), key=lambda item: str(item["path"]))
    return _build_evidence_index(entries, label=label)


def _build_evidence_index(entries: list[JsonDict], *, label: str) -> JsonDict:
    public_entries = [_public_safe_entry(entry) for entry in entries]
    return redact_sensitive(
        {
            "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
            "label": label,
            "field_map_version": ASHR_API_FIELD_MAP_VERSION,
            "total_records": len(public_entries),
            "status_counts": _count_by(public_entries, "status"),
            "function_counts": _count_by(public_entries, "function"),
            "error_kind_counts": _count_by(public_entries, "error_kind"),
            "quota_block_count": sum(1 for entry in public_entries if entry.get("quota") and entry["quota"].get("blocked") is True),
            "output_policy_counts": _output_policy_counts(public_entries),
            "records": public_entries,
        }
    )


def _records_by_path(records: Any) -> dict[str, JsonDict]:
    if not isinstance(records, list):
        return {}
    indexed: dict[str, JsonDict] = {}
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            continue
        indexed[record["path"]] = dict(record)
    return indexed


def _public_safe_entry(entry: Mapping[str, Any]) -> JsonDict:
    public_entry = dict(entry)
    quota = public_entry.get("quota")
    if isinstance(quota, Mapping):
        public_quota = _public_safe_quota_summary(quota)
        if public_quota:
            public_entry["quota"] = public_quota
        else:
            public_entry.pop("quota", None)
    return redact_sensitive(public_entry)


def build_private_evidence_index_from_dir(root: str | Path, options: EvidenceIndexOptions | None = None) -> JsonDict:
    opts = options or EvidenceIndexOptions()
    root_path = Path(root)
    paths: list[Path] = []
    for pattern in opts.include_patterns:
        paths.extend(path for path in root_path.glob(pattern) if path.is_file())
    unique_paths = sorted(set(paths))
    if opts.max_files is not None:
        unique_paths = unique_paths[: opts.max_files]
    return build_private_evidence_index(unique_paths, label=opts.label)


def write_private_evidence_index(path: str | Path, index: Mapping[str, Any], *, strict_public: bool = False) -> Path:
    if strict_public:
        assert_public_evidence_index_safe(index)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(redact_sensitive(dict(index)), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def assert_public_evidence_index_safe(index: Mapping[str, Any]) -> None:
    issues = validate_public_evidence_index(index)
    blocking = [issue for issue in issues if issue.get("severity") == "error"]
    if blocking:
        raise PublicEvidenceIndexError(blocking)


def scan_tracked_public_evidence_artifacts(repo_root: str | Path, *, public_root: str = "docs/a1/evidence") -> list[JsonDict]:
    """Scan tracked public A1 evidence artifacts for leak-shaped secret markers."""

    root = Path(repo_root)
    paths = _tracked_public_evidence_paths(root, public_root)
    issues: list[JsonDict] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append({"severity": "error", "kind": "non_utf8_public_evidence", "path": _repo_relative_path(root, path)})
            continue
        issues.extend(scan_public_evidence_artifact_text(text, path=_repo_relative_path(root, path)))
    return issues


def scan_public_evidence_artifact_text(text: str, *, path: str = "<memory>") -> list[JsonDict]:
    issues: list[JsonDict] = []
    for kind, pattern in _PUBLIC_ARTIFACT_SECRET_MARKERS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            issues.append({"severity": "error", "kind": kind, "path": path, "line": line, "pattern": pattern.pattern})
    return issues


def validate_public_evidence_index(index: Mapping[str, Any]) -> list[JsonDict]:
    issues: list[JsonDict] = []
    raw_text = json.dumps(dict(index), sort_keys=True)
    text = json.dumps(redact_sensitive(dict(index)), sort_keys=True)
    for pattern in ("5/5 " + "used", '"remaining": ' + "0", '"requested": ' + "1", '"used": ' + "5"):
        if pattern in text:
            issues.append({"severity": "error", "kind": "exact_quota_detail", "pattern": pattern})
    for pattern in _PUBLIC_SECRET_PATTERNS:
        if pattern.search(raw_text):
            issues.append({"severity": "error", "kind": "secret_like_text", "pattern": pattern.pattern})
    records = index.get("records") if isinstance(index.get("records"), list) else []
    for offset, record in enumerate(records):
        if not isinstance(record, Mapping):
            issues.append({"severity": "error", "kind": "malformed_record", "record_index": offset})
            continue
        output_policy = record.get("output_policy")
        if output_policy is None:
            pass
        elif not isinstance(output_policy, Mapping):
            issues.append({"severity": "error", "kind": "malformed_output_policy", "record_index": offset})
        else:
            if output_policy.get("schema_version") != OUTPUT_POLICY_SCHEMA_VERSION:
                issues.append({"severity": "error", "kind": "bad_output_policy_schema", "record_index": offset})
            if _is_unsafe_real_nonprivate_override(record):
                issues.append({"severity": "error", "kind": "unsafe_real_nonprivate_output_override", "record_index": offset})
            if output_policy.get("private_output_required") is True and output_policy.get("output_is_private") is not True:
                issues.append({"severity": "error", "kind": "private_required_but_not_private", "record_index": offset})
            unsafe_path = _unsafe_output_policy_path(output_policy.get("resolved_under_repo"))
            if unsafe_path:
                issues.append({"severity": "error", "kind": "unsafe_output_policy_path", "record_index": offset, "field": "resolved_under_repo"})
        quota = record.get("quota")
        if not isinstance(quota, Mapping):
            continue
        for key in ("limit", "used", "requested", "remaining"):
            if key in quota:
                issues.append({"severity": "error", "kind": "quota_value_not_public_safe", "record_index": offset, "field": key})
    return issues


def build_response_field_map(index: Mapping[str, Any]) -> JsonDict:
    records = index.get("records") if isinstance(index.get("records"), list) else []
    functions: dict[str, JsonDict] = {}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        function = str(record.get("function") or "unknown")
        item = functions.setdefault(
            function,
            {
                "records": 0,
                "statuses": {},
                "response_keys": [],
                "response_summary_keys": [],
                "error_keys": [],
                "quota_block_count": 0,
                "top_count_keys": [],
            },
        )
        item["records"] += 1
        status = record.get("status")
        if status is not None:
            statuses = item["statuses"]
            statuses[str(status)] = statuses.get(str(status), 0) + 1
        for source_key, target_key in (("response_keys", "response_keys"), ("response_summary_keys", "response_summary_keys"), ("error_keys", "error_keys")):
            merged = set(item[target_key])
            merged.update(str(key) for key in record.get(source_key, []) if isinstance(key, str))
            item[target_key] = sorted(merged)
        top_counts = record.get("top_counts") if isinstance(record.get("top_counts"), Mapping) else {}
        merged_top = set(item["top_count_keys"])
        merged_top.update(str(key) for key in top_counts.keys())
        item["top_count_keys"] = sorted(merged_top)
        quota = record.get("quota") if isinstance(record.get("quota"), Mapping) else {}
        if quota.get("blocked") is True:
            item["quota_block_count"] += 1
    return {
        "schema_version": "ashr.clone.response_field_map.v1",
        "source_label": index.get("label"),
        "source_total_records": index.get("total_records"),
        "field_map_version": index.get("field_map_version"),
        "functions": dict(sorted(functions.items())),
    }


def render_response_field_map_markdown(field_map: Mapping[str, Any]) -> str:
    functions = field_map.get("functions") if isinstance(field_map.get("functions"), Mapping) else {}
    lines = [
        "# Ashr Real API Response Field Map",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Schema | `{field_map.get('schema_version', '')}` |",
        f"| Source label | `{field_map.get('source_label', '')}` |",
        f"| Source records | `{field_map.get('source_total_records', '')}` |",
        f"| Field map version | `{field_map.get('field_map_version', '')}` |",
        "",
        "## Function Coverage",
        "",
        "| Function | Records | Statuses | Response keys | Error keys | Top count keys | Quota blocks |",
        "| --- | ---: | --- | --- | --- | --- | ---: |",
    ]
    for function_name, details in sorted(functions.items()):
        if not isinstance(details, Mapping):
            continue
        lines.append(
            "| {function} | {records} | {statuses} | {response_keys} | {error_keys} | {top_count_keys} | {quota_blocks} |".format(
                function=_md_code(function_name),
                records=details.get("records", 0),
                statuses=_format_counts(details.get("statuses")),
                response_keys=_format_inline_list(details.get("response_keys")),
                error_keys=_format_inline_list(details.get("error_keys")),
                top_count_keys=_format_inline_list(details.get("top_count_keys")),
                quota_blocks=details.get("quota_block_count", 0),
            )
        )
    lines.extend(
        [
            "",
            "## Commercial Readiness Notes",
            "",
            "- Public report intentionally lists field names, statuses, and quota-block presence only; exact hosted quota counts and raw payloads remain in ignored private evidence.",
            "- Functions with quota blocks need quota-reset or plan-upgrade confirmation before paid mutating probes are scaled.",
            "- Functions with both ok and error statuses are candidates for typed error taxonomy and replay fixture hardening.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_response_field_map_markdown(path: str | Path, field_map: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_response_field_map_markdown(field_map), encoding="utf-8")
    return output


def _summarize_record_path(path: Path) -> JsonDict | None:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(record, Mapping):
        return None
    response = record.get("response") if isinstance(record.get("response"), Mapping) else {}
    error = record.get("error") if isinstance(record.get("error"), Mapping) else {}
    request = record.get("request") if isinstance(record.get("request"), Mapping) else {}
    quota = _public_safe_quota_summary(summarize_quota_error(record))
    entry: JsonDict = {
        "path": _repo_relative_path(Path.cwd(), path.resolve()),
        "function": record.get("function"),
        "dry_run": record.get("dry_run"),
        "status": record.get("status"),
        "status_code": record.get("status_code"),
        "attempts": record.get("attempts"),
        "request_keys": _keys(request),
        "response_keys": _keys(response),
        "response_status": response.get("status") if isinstance(response.get("status"), str) else None,
        "response_summary_keys": _keys(record.get("response_summary")),
        "error_keys": _keys(error),
        "error_kind": error.get("error_kind") if isinstance(error.get("error_kind"), str) else None,
        "top_counts": _top_counts(response),
    }
    output_policy = _public_safe_output_policy(record.get("output_policy"))
    if output_policy:
        entry["output_policy"] = output_policy
    if quota:
        entry["quota"] = quota
    return redact_sensitive(entry)


def _public_safe_output_policy(value: Any) -> JsonDict | None:
    if not isinstance(value, Mapping):
        return None
    allowed = {
        "schema_version",
        "private_output_required",
        "allow_nonprivate_output",
        "nonprivate_output_override_used",
        "output_is_private",
        "sink",
        "private_root",
        "resolved_under_repo",
        "full_record_stdout_blocked",
        "record_class",
        "producer",
        "policy_decision",
        "resolved_under_private_root",
        "resolved_outside_repo",
        "stdout_full_record_requested",
    }
    return {str(key): value.get(key) for key in allowed if key in value}


def _public_safe_quota_summary(quota: Mapping[str, Any] | None) -> JsonDict | None:
    if not quota:
        return None
    quota_keys = quota.get("quota_keys") if isinstance(quota.get("quota_keys"), list) else []
    summary: JsonDict = {
        "blocked": quota.get("blocked") is True,
        "message": "Usage limit exceeded; exact quota details are kept in private evidence" if quota.get("blocked") is True else None,
        "quota_keys": sorted(str(key) for key in quota_keys),
    }
    resource = quota.get("resource")
    if isinstance(resource, (str, int, float, bool)):
        summary["resource"] = resource
    for key in ("limit", "used", "requested", "remaining"):
        if key in quota or f"{key}_present" in quota or key in quota_keys:
            summary[f"{key}_present"] = True
    return summary


def _keys(value: Any) -> list[str]:
    return sorted(str(key) for key in value.keys()) if isinstance(value, Mapping) else []


def _top_counts(response: Mapping[str, Any]) -> JsonDict:
    counts: JsonDict = {}
    for key in ("agents", "datasets", "requests", "runs"):
        value = response.get(key)
        if isinstance(value, list):
            counts[key] = len(value)
    return counts


def _count_by(entries: Iterable[Mapping[str, Any]], key: str) -> JsonDict:
    counts: dict[str, int] = {}
    for entry in entries:
        value = entry.get(key)
        if value is None:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _format_counts(value: Any) -> str:
    if not isinstance(value, Mapping) or not value:
        return "-"
    return ", ".join(f"{_md_code(str(key))}: {count}" for key, count in sorted(value.items()))


def _format_inline_list(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "-"
    return ", ".join(_md_code(str(item)) for item in value)


def _md_code(value: str) -> str:
    return "`" + value.replace("`", "\\`").replace("|", "\\|") + "`"


def _count_nested(entries: Iterable[Mapping[str, Any]], outer_key: str, inner_key: str) -> JsonDict:
    counts: dict[str, int] = {}
    for entry in entries:
        outer = entry.get(outer_key)
        if not isinstance(outer, Mapping):
            continue
        value = outer.get(inner_key)
        if value is None:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _output_policy_counts(entries: Iterable[Mapping[str, Any]]) -> JsonDict:
    counts: JsonDict = {
        "missing": 0,
        "present": 0,
        "private_required": 0,
        "private_not_required": 0,
        "private_file": 0,
        "nonprivate_file": 0,
        "stdout": 0,
        "none": 0,
        "nonprivate_override": 0,
        "unsafe_real_nonprivate_override": 0,
        "stdout_full_record_blocked": 0,
        "stdout_full_record_requested": 0,
        "resolved_outside_repo": 0,
        "resolved_under_private_root": 0,
        "private_required_but_not_private": 0,
        "sink": {"private_file": 0, "nonprivate_file": 0, "stdout": 0, "none": 0},
        "by_record_class": {},
        "by_producer": {},
    }
    for entry in entries:
        policy = entry.get("output_policy")
        if not isinstance(policy, Mapping):
            counts["missing"] += 1
            continue
        counts["present"] += 1
        if policy.get("private_output_required") is True:
            counts["private_required"] += 1
            if policy.get("output_is_private") is not True:
                counts["private_required_but_not_private"] += 1
        elif policy.get("private_output_required") is False:
            counts["private_not_required"] += 1
        sink = policy.get("sink")
        if sink in counts["sink"]:
            counts["sink"][sink] += 1
            counts[sink] += 1
        if policy.get("nonprivate_output_override_used") is True:
            counts["nonprivate_override"] += 1
        if _is_unsafe_real_nonprivate_override(entry):
            counts["unsafe_real_nonprivate_override"] += 1
        if policy.get("full_record_stdout_blocked") is True:
            counts["stdout_full_record_blocked"] += 1
        if policy.get("stdout_full_record_requested") is True:
            counts["stdout_full_record_requested"] += 1
        if policy.get("resolved_outside_repo") is True or policy.get("resolved_under_repo") == "<outside-repo>":
            counts["resolved_outside_repo"] += 1
        if policy.get("resolved_under_private_root") is True:
            counts["resolved_under_private_root"] += 1
        record_class = policy.get("record_class")
        if isinstance(record_class, str):
            by_record_class = counts["by_record_class"]
            by_record_class[record_class] = by_record_class.get(record_class, 0) + 1
        producer = policy.get("producer")
        if isinstance(producer, str):
            by_producer = counts["by_producer"]
            by_producer[producer] = by_producer.get(producer, 0) + 1
    counts["sink"] = dict(sorted(counts["sink"].items()))
    counts["by_record_class"] = dict(sorted(counts["by_record_class"].items()))
    counts["by_producer"] = dict(sorted(counts["by_producer"].items()))
    return counts


def _is_unsafe_real_nonprivate_override(record: Mapping[str, Any]) -> bool:
    policy = record.get("output_policy")
    if not isinstance(policy, Mapping):
        return False
    is_real = record.get("dry_run") is False or policy.get("record_class") in _REAL_RECORD_CLASSES
    return bool(is_real and policy.get("private_output_required") is True and policy.get("nonprivate_output_override_used") is True)


def _unsafe_output_policy_path(value: Any) -> bool:
    if value is None or value == "<outside-repo>":
        return False
    if not isinstance(value, str):
        return True
    return bool(re.match(r"^[A-Za-z]:", value) or value.startswith("/") or "\\" in value or any(part == ".." for part in value.split("/")))


def _tracked_public_evidence_paths(repo_root: Path, public_root: str) -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "--", public_root],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [repo_root / line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _repo_relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()
