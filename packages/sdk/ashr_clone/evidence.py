from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .api_client import ASHR_API_FIELD_MAP_VERSION, redact_sensitive, summarize_quota_error

JsonDict = dict[str, Any]
EVIDENCE_INDEX_SCHEMA_VERSION = "ashr.clone.evidence_index.v1"


@dataclass(slots=True)
class EvidenceIndexOptions:
    include_patterns: tuple[str, ...] = ("*.json",)
    max_files: int | None = None
    label: str = "a1-real-api"


def build_private_evidence_index(paths: Iterable[str | Path], *, label: str = "a1-real-api") -> JsonDict:
    entries = [_summarize_record_path(Path(path)) for path in paths]
    entries = [entry for entry in entries if entry is not None]
    entries.sort(key=lambda item: str(item["path"]))
    return redact_sensitive(
        {
            "schema_version": EVIDENCE_INDEX_SCHEMA_VERSION,
            "label": label,
            "field_map_version": ASHR_API_FIELD_MAP_VERSION,
            "total_records": len(entries),
            "status_counts": _count_by(entries, "status"),
            "function_counts": _count_by(entries, "function"),
            "error_kind_counts": _count_by(entries, "error_kind"),
            "quota_block_count": sum(1 for entry in entries if entry.get("quota") and entry["quota"].get("blocked") is True),
            "records": entries,
        }
    )


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
    quota = summarize_quota_error(record)
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