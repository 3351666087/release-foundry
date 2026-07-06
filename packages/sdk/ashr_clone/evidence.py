from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .api_client import ASHR_API_FIELD_MAP_VERSION, redact_sensitive, summarize_quota_error

JsonDict = dict[str, Any]
EVIDENCE_INDEX_SCHEMA_VERSION = "ashr.clone.evidence_index.v1"
_PUBLIC_SECRET_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"ashr_live_[A-Za-z0-9_\-]+"),
)


@dataclass(slots=True)
class EvidenceIndexOptions:
    include_patterns: tuple[str, ...] = ("*.json",)
    max_files: int | None = None
    label: str = "a1-real-api"


def build_private_evidence_index(paths: Iterable[str | Path], *, label: str = "a1-real-api") -> JsonDict:
    entries = [_summarize_record_path(Path(path)) for path in paths]
    entries = [entry for entry in entries if entry is not None]
    entries.sort(key=lambda item: str(item["path"]))
    return _build_evidence_index(entries, label=label)


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


def write_private_evidence_index(path: str | Path, index: Mapping[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(redact_sensitive(dict(index)), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


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
        "path": path.as_posix(),
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
    if quota:
        entry["quota"] = quota
    return redact_sensitive(entry)


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
