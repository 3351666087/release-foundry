from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .evidence import JsonDict, _is_unsafe_real_nonprivate_override, validate_public_evidence_index

LEGACY_EVIDENCE_SCAN_SCHEMA_VERSION = "ashr.clone.legacy_evidence_scan.v1"
DEFAULT_EXPECTED_RECORD_CLASSES = ("dry_run_plan", "real_readonly", "real_mutating", "quota_gate")
DEFAULT_EXPECTED_PRODUCERS = (
    "packages.sdk.ashr_clone.api_client",
    "packages.sdk.ashr_clone.calibrate",
    "services.runner.api_probe",
)
_MUTATING_FUNCTION_PREFIXES = ("create_", "update_", "delete_", "evaluate_", "revoke_", "set_")


def load_public_legacy_evidence_scan(
    index_path: str | Path,
    *,
    expected_record_classes: Iterable[str] = DEFAULT_EXPECTED_RECORD_CLASSES,
    expected_producers: Iterable[str] = DEFAULT_EXPECTED_PRODUCERS,
    sample_limit: int = 20,
) -> JsonDict:
    """Scan a public-safe evidence index for legacy output-policy gaps.

    This function intentionally reads only the supplied public index JSON. Record
    ``path`` values are treated as opaque public metadata; the referenced private
    evidence files are never opened.
    """

    path = Path(index_path)
    index = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(index, Mapping):
        raise ValueError("legacy evidence scan requires a JSON object evidence index")
    scan = scan_legacy_evidence_index(
        index,
        expected_record_classes=expected_record_classes,
        expected_producers=expected_producers,
        sample_limit=sample_limit,
    )
    scan["source_path"] = path.as_posix()
    return scan


def scan_legacy_evidence_index(
    index: Mapping[str, Any],
    *,
    expected_record_classes: Iterable[str] = DEFAULT_EXPECTED_RECORD_CLASSES,
    expected_producers: Iterable[str] = DEFAULT_EXPECTED_PRODUCERS,
    sample_limit: int = 20,
) -> JsonDict:
    records = [record for record in index.get("records", []) if isinstance(record, Mapping)] if isinstance(index.get("records"), list) else []
    missing_policy_records = [record for record in records if not isinstance(record.get("output_policy"), Mapping)]
    policies = [record.get("output_policy") for record in records if isinstance(record.get("output_policy"), Mapping)]
    public_issues = validate_public_evidence_index(index)
    blocking_issues = [issue for issue in public_issues if issue.get("severity") == "error"]

    return {
        "schema_version": LEGACY_EVIDENCE_SCAN_SCHEMA_VERSION,
        "source_label": index.get("label"),
        "source_schema_version": index.get("schema_version"),
        "source_total_records": index.get("total_records", len(records)),
        "scanned_records": len(records),
        "legacy_record_summary": _legacy_record_summary(missing_policy_records, sample_limit=sample_limit),
        "producer_class_coverage_gaps": _producer_class_coverage_gaps(
            records,
            policies,
            expected_record_classes=tuple(str(value) for value in expected_record_classes),
            expected_producers=tuple(str(value) for value in expected_producers),
        ),
        "blocking_unsafe_counts": _blocking_unsafe_counts(index, records, missing_policy_records, blocking_issues),
    }


def _legacy_record_summary(records: list[Mapping[str, Any]], *, sample_limit: int) -> JsonDict:
    quota_blocked = [record for record in records if _quota_blocked(record)]
    real_records = [record for record in records if record.get("dry_run") is False]
    mutating_records = [record for record in records if _is_mutating_function(record.get("function"))]
    return {
        "missing_output_policy": len(records),
        "real_missing_output_policy": len(real_records),
        "dry_run_missing_output_policy": sum(1 for record in records if record.get("dry_run") is True),
        "mutating_function_missing_output_policy": len(mutating_records),
        "quota_blocked_missing_output_policy": len(quota_blocked),
        "by_function": _counter(records, "function"),
        "by_status": _counter(records, "status"),
        "by_dry_run": _counter_bool(records, "dry_run"),
        "samples": [_legacy_record_sample(record) for record in records[: max(sample_limit, 0)]],
    }


def _producer_class_coverage_gaps(
    records: list[Mapping[str, Any]],
    policies: list[Any],
    *,
    expected_record_classes: tuple[str, ...],
    expected_producers: tuple[str, ...],
) -> JsonDict:
    by_record_class = Counter(str(policy.get("record_class")) for policy in policies if isinstance(policy.get("record_class"), str))
    by_producer = Counter(str(policy.get("producer")) for policy in policies if isinstance(policy.get("producer"), str))
    missing_record_class_records = sum(1 for policy in policies if not isinstance(policy.get("record_class"), str))
    missing_producer_records = sum(1 for policy in policies if not isinstance(policy.get("producer"), str))
    records_without_policy = len(records) - len(policies)
    missing_expected_record_classes = sorted(value for value in expected_record_classes if value not in by_record_class)
    missing_expected_producers = sorted(value for value in expected_producers if value not in by_producer)
    gaps: list[JsonDict] = []
    if records_without_policy:
        gaps.append({"kind": "records_without_output_policy", "count": records_without_policy})
    if missing_record_class_records:
        gaps.append({"kind": "policies_without_record_class", "count": missing_record_class_records})
    if missing_producer_records:
        gaps.append({"kind": "policies_without_producer", "count": missing_producer_records})
    gaps.extend({"kind": "missing_expected_record_class", "record_class": value} for value in missing_expected_record_classes)
    gaps.extend({"kind": "missing_expected_producer", "producer": value} for value in missing_expected_producers)
    return {
        "by_record_class": dict(sorted(by_record_class.items())),
        "by_producer": dict(sorted(by_producer.items())),
        "records_without_output_policy": records_without_policy,
        "policies_without_record_class": missing_record_class_records,
        "policies_without_producer": missing_producer_records,
        "missing_expected_record_classes": missing_expected_record_classes,
        "missing_expected_producers": missing_expected_producers,
        "gaps": gaps,
    }


def _blocking_unsafe_counts(
    index: Mapping[str, Any], records: list[Mapping[str, Any]], missing_policy_records: list[Mapping[str, Any]], issues: list[Mapping[str, Any]]) -> JsonDict:
    issue_counts = Counter(str(issue.get("kind", "unknown")) for issue in issues)
    output_policy_counts = index.get("output_policy_counts") if isinstance(index.get("output_policy_counts"), Mapping) else {}
    return {
        "blocking_issue_count": len(issues),
        "blocking_issue_counts_by_kind": dict(sorted(issue_counts.items())),
        "unsafe_real_nonprivate_override": int(output_policy_counts.get("unsafe_real_nonprivate_override", 0) or 0),
        "private_required_but_not_private": int(output_policy_counts.get("private_required_but_not_private", 0) or 0),
        "quota_block_count": int(index.get("quota_block_count", 0) or 0),
        "quota_blocked_missing_output_policy": sum(1 for record in missing_policy_records if _quota_blocked(record)),
        "real_nonprivate_override_records": sum(1 for record in records if _is_unsafe_real_nonprivate_override(record)),
    }


def _legacy_record_sample(record: Mapping[str, Any]) -> JsonDict:
    return {
        "path": record.get("path"),
        "function": record.get("function"),
        "dry_run": record.get("dry_run"),
        "status": record.get("status"),
        "status_code": record.get("status_code"),
        "error_kind": record.get("error_kind"),
        "quota_blocked": _quota_blocked(record),
    }


def _counter(records: Iterable[Mapping[str, Any]], key: str) -> JsonDict:
    counts = Counter(str(record.get(key)) for record in records if record.get(key) is not None)
    return dict(sorted(counts.items()))


def _counter_bool(records: Iterable[Mapping[str, Any]], key: str) -> JsonDict:
    counts: Counter[str] = Counter()
    for record in records:
        value = record.get(key)
        if value is True:
            counts["true"] += 1
        elif value is False:
            counts["false"] += 1
        else:
            counts["unknown"] += 1
    return dict(sorted(counts.items()))


def _quota_blocked(record: Mapping[str, Any]) -> bool:
    quota = record.get("quota")
    return bool(isinstance(quota, Mapping) and quota.get("blocked") is True)


def _is_mutating_function(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_MUTATING_FUNCTION_PREFIXES)
