from __future__ import annotations

from pathlib import Path

from packages.sdk.ashr_clone.evidence_legacy import load_public_legacy_evidence_scan, scan_legacy_evidence_index


def test_legacy_evidence_scan_reads_public_index_only_and_reports_round14_gaps():
    root = Path(__file__).resolve().parents[2]
    index_path = root / "docs" / "a1" / "api_calibration" / "real_api_evidence_index.json"

    scan = load_public_legacy_evidence_scan(index_path, sample_limit=3)

    assert scan["schema_version"] == "ashr.clone.legacy_evidence_scan.v1"
    assert scan["source_path"].endswith("docs/a1/api_calibration/real_api_evidence_index.json")
    assert scan["scanned_records"] >= 337
    assert scan["legacy_record_summary"]["missing_output_policy"] == 337
    assert scan["legacy_record_summary"]["real_missing_output_policy"] > 0
    assert scan["legacy_record_summary"]["quota_blocked_missing_output_policy"] == scan["blocking_unsafe_counts"]["quota_blocked_missing_output_policy"]
    assert len(scan["legacy_record_summary"]["samples"]) == 3
    assert all("docs/evidence/private_refs" in sample["path"] for sample in scan["legacy_record_summary"]["samples"])
    assert scan["producer_class_coverage_gaps"]["records_without_output_policy"] >= 337
    assert "dry_run_plan" in scan["producer_class_coverage_gaps"]["missing_expected_record_classes"]
    assert "packages.sdk.ashr_clone.api_client" in scan["producer_class_coverage_gaps"]["missing_expected_producers"]
    assert scan["blocking_unsafe_counts"]["blocking_issue_count"] == 0
    assert scan["blocking_unsafe_counts"]["quota_block_count"] == 41


def test_legacy_evidence_scan_summarizes_policy_coverage_and_blocking_unsafe_counts():
    index = {
        "schema_version": "ashr.clone.evidence_index.v1",
        "label": "unit",
        "total_records": 4,
        "quota_block_count": 1,
        "output_policy_counts": {"unsafe_real_nonprivate_override": 1, "private_required_but_not_private": 1},
        "records": [
            {
                "path": "docs/evidence/private_refs/legacy-real.json",
                "function": "create_run",
                "dry_run": False,
                "status": "ok",
                "status_code": 200,
            },
            {
                "path": "docs/evidence/private_refs/legacy-quota.json",
                "function": "create_request",
                "dry_run": False,
                "status": "error",
                "quota": {"blocked": True, "quota_keys": ["limit_present"]},
            },
            {
                "path": "docs/evidence/private_refs/private.json",
                "function": "list_runs",
                "dry_run": False,
                "status": "ok",
                "output_policy": {
                    "schema_version": "ashr.clone.output_policy.v1",
                    "private_output_required": True,
                    "allow_nonprivate_output": False,
                    "nonprivate_output_override_used": False,
                    "output_is_private": True,
                    "sink": "private_file",
                    "private_root": "docs/evidence/private_refs",
                    "resolved_under_repo": "docs/evidence/private_refs/private.json",
                    "full_record_stdout_blocked": True,
                    "record_class": "real_readonly",
                    "producer": "packages.sdk.ashr_clone.api_client",
                },
            },
            {
                "path": "tmp/unsafe.json",
                "function": "create_request",
                "dry_run": False,
                "status": "ok",
                "output_policy": {
                    "schema_version": "ashr.clone.output_policy.v1",
                    "private_output_required": True,
                    "allow_nonprivate_output": True,
                    "nonprivate_output_override_used": True,
                    "output_is_private": False,
                    "sink": "nonprivate_file",
                    "private_root": "docs/evidence/private_refs",
                    "resolved_under_repo": "tmp/unsafe.json",
                    "full_record_stdout_blocked": False,
                    "record_class": "real_mutating",
                    "producer": "services.runner.api_probe",
                },
            },
        ],
    }

    scan = scan_legacy_evidence_index(index, expected_record_classes=("real_readonly", "real_mutating"), expected_producers=("packages.sdk.ashr_clone.api_client", "services.runner.api_probe"))

    assert scan["legacy_record_summary"]["missing_output_policy"] == 2
    assert scan["legacy_record_summary"]["real_missing_output_policy"] == 2
    assert scan["legacy_record_summary"]["mutating_function_missing_output_policy"] == 2
    assert scan["legacy_record_summary"]["quota_blocked_missing_output_policy"] == 1
    assert scan["producer_class_coverage_gaps"]["by_record_class"] == {"real_mutating": 1, "real_readonly": 1}
    assert scan["producer_class_coverage_gaps"]["by_producer"] == {"packages.sdk.ashr_clone.api_client": 1, "services.runner.api_probe": 1}
    assert scan["producer_class_coverage_gaps"]["missing_expected_record_classes"] == []
    assert scan["producer_class_coverage_gaps"]["records_without_output_policy"] == 2
    assert scan["blocking_unsafe_counts"]["unsafe_real_nonprivate_override"] == 1
    assert scan["blocking_unsafe_counts"]["private_required_but_not_private"] == 1
    assert scan["blocking_unsafe_counts"]["real_nonprivate_override_records"] == 1
    assert scan["blocking_unsafe_counts"]["blocking_issue_counts_by_kind"] == {
        "private_required_but_not_private": 1,
        "unsafe_real_nonprivate_output_override": 1,
    }

